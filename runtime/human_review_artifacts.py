"""Derived, immutable presentation artefacts for authorised human review.

The structured workflow artefact remains authoritative.  This module selects
review-relevant editorial content, renders it through a reusable Narratiive PDF
system, and records exact source/output lineage without exposing runtime audit
metadata in the visible document.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfReader

from runtime.models import ArtifactRef, WorkflowState


RENDERER_ID = "narratiive-human-review-pdf"
RENDERER_VERSION = "2"
BLUEPRINT_PRESENTATION_RENDERER_ID = "narratiive-growth-blueprint-presentation"
BLUEPRINT_PRESENTATION_RENDERER_VERSION = "1"
PDF_MIME_TYPE = "application/pdf"

INK = colors.HexColor("#20201D")
IVORY = colors.HexColor("#F4EFE4")
AMBER = colors.HexColor("#C88632")
STONE = colors.HexColor("#777269")
PALE = colors.HexColor("#E5DED0")
WHITE = colors.white

PROHIBITED_VISIBLE_FIELDS = frozenset(
    {
        "provider_message_id",
        "stop_reason",
        "worker_id",
        "worker_execution",
        "policy_id",
        "selection_reason",
        "source_refs",
        "artifact_id",
        "workflow_id",
        "run_id",
        "raw json",
    }
)


class HumanReviewArtifactError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewSection:
    heading: str
    body: tuple[str, ...] = ()
    items: tuple[str, ...] = ()
    cards: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewDocumentPlan:
    product: str
    gate_label: str
    company: str
    subtitle: str
    sections: tuple[ReviewSection, ...]
    focus_points: tuple[str, ...]
    decision_prompt: str
    next_if_approved: str


@dataclass(frozen=True, slots=True)
class HumanReviewArtifact:
    review_artifact_id: str
    source_artifact_id: str
    source_artifact_checksum: str
    renderer_id: str
    renderer_version: str
    product: str
    filename: str
    mime_type: str
    location: str
    checksum: str
    page_count: int
    focus_points: tuple[str, ...]
    decision_prompt: str
    next_if_approved: str
    telegram_notification: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["focus_points"] = list(self.focus_points)
        return value


class HumanReviewArtifactStore:
    """Content-addressed store for derived review PDFs and lineage manifests."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def persist(
        self,
        *,
        state: WorkflowState,
        source: ArtifactRef,
        plan: ReviewDocumentPlan,
        pdf_bytes: bytes,
        page_count: int,
        renderer_id: str = RENDERER_ID,
        renderer_version: str = RENDERER_VERSION,
    ) -> HumanReviewArtifact:
        source_checksum = str(source.checksum or "").strip()
        if not source_checksum:
            raise HumanReviewArtifactError("source artefact checksum is required")
        identity = hashlib.sha256(
            "\0".join(
                (
                    state.workspace_id,
                    state.client_id,
                    state.run_id,
                    source.artifact_id,
                    source_checksum,
                    renderer_id,
                    renderer_version,
                )
            ).encode("utf-8")
        ).hexdigest()
        review_artifact_id = f"review-{identity[:24]}"
        filename = (
            f"{_safe_filename(plan.company)}-{_safe_filename(plan.product)}-"
            f"review-{source_checksum[:8]}.pdf"
        )
        directory = (
            self.root
            / _safe_path_component(state.workspace_id, "workspace_id")
            / _safe_path_component(state.client_id, "client_id")
            / review_artifact_id
        )
        target = directory / filename
        manifest = directory / "manifest.json"
        checksum = hashlib.sha256(pdf_bytes).hexdigest()
        telegram_notification = _telegram_notification(plan)
        record = HumanReviewArtifact(
            review_artifact_id=review_artifact_id,
            source_artifact_id=source.artifact_id,
            source_artifact_checksum=source_checksum,
            renderer_id=renderer_id,
            renderer_version=renderer_version,
            product=plan.product,
            filename=filename,
            mime_type=PDF_MIME_TYPE,
            location=str(target),
            checksum=checksum,
            page_count=page_count,
            focus_points=plan.focus_points,
            decision_prompt=plan.decision_prompt,
            next_if_approved=plan.next_if_approved,
            telegram_notification=telegram_notification,
        )
        manifest_bytes = (json.dumps(record.to_dict(), sort_keys=True, indent=2) + "\n").encode("utf-8")
        directory.mkdir(parents=True, exist_ok=True)
        _persist_immutable(target, pdf_bytes)
        _persist_immutable(manifest, manifest_bytes)
        return record


class HumanReviewPresentationService:
    """Build a product-aware human review PDF from one canonical artefact."""

    def __init__(
        self,
        store: HumanReviewArtifactStore,
        *,
        allowed_source_root: str | Path | None = None,
    ) -> None:
        self.store = store
        self.allowed_source_root = Path(allowed_source_root).resolve() if allowed_source_root else None

    def produce(
        self,
        *,
        state: WorkflowState,
        source: ArtifactRef,
        output: Mapping[str, Any],
    ) -> HumanReviewArtifact:
        if state.workflow_id == "growth_blueprint_deliverable_production":
            return self._ingest_growth_blueprint_review(state=state, source=source, output=output)
        plan = build_review_plan(state, output)
        _validate_review_plan(plan)
        pdf_bytes, pages = NarratiiveReviewPDFRenderer().render(plan)
        return self.store.persist(
            state=state,
            source=source,
            plan=plan,
            pdf_bytes=pdf_bytes,
            page_count=pages,
        )

    def _ingest_growth_blueprint_review(
        self,
        *,
        state: WorkflowState,
        source: ArtifactRef,
        output: Mapping[str, Any],
    ) -> HumanReviewArtifact:
        if self.allowed_source_root is None:
            raise HumanReviewArtifactError("Growth Blueprint review ingestion requires an allowed source root")
        visual_qa = output.get("visual_qa")
        checks = visual_qa.get("checks") if isinstance(visual_qa, Mapping) else None
        if (
            not isinstance(visual_qa, Mapping)
            or visual_qa.get("status") != "passed"
            or not isinstance(checks, Mapping)
            or checks.get("no_visible_machine_runtime_artefacts") is not True
        ):
            raise HumanReviewArtifactError("Growth Blueprint review PDF has not passed presentation QA")
        if output.get("approval_status") != "pending" or output.get("external_action_taken") is not False:
            raise HumanReviewArtifactError("Growth Blueprint presentation is not at a pending internal gate")
        review_path = Path(str(output.get("review_pdf") or ""))
        if not review_path.is_absolute():
            review_path = (Path(source.location).resolve().parent / review_path).resolve()
        else:
            review_path = review_path.resolve()
        try:
            review_path.relative_to(self.allowed_source_root)
        except ValueError as exc:
            raise HumanReviewArtifactError("Growth Blueprint review PDF is outside the authoritative runtime root") from exc
        if review_path.suffix.casefold() != ".pdf" or not review_path.is_file():
            raise HumanReviewArtifactError("Growth Blueprint review PDF is missing")
        pdf_bytes = review_path.read_bytes()
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            visible = "\n".join(page.extract_text() or "" for page in reader.pages).casefold()
        except Exception as exc:
            raise HumanReviewArtifactError("Growth Blueprint review PDF is unreadable") from exc
        leaked = sorted(field for field in PROHIBITED_VISIBLE_FIELDS if field in visible)
        if leaked:
            raise HumanReviewArtifactError(
                "Growth Blueprint review PDF exposes internal field names: " + ", ".join(leaked)
            )
        plan = _produced_growth_blueprint_plan(_company_name(state), output)
        _validate_review_plan(plan)
        return self.store.persist(
            state=state,
            source=source,
            plan=plan,
            pdf_bytes=pdf_bytes,
            page_count=len(reader.pages),
            renderer_id=BLUEPRINT_PRESENTATION_RENDERER_ID,
            renderer_version=BLUEPRINT_PRESENTATION_RENDERER_VERSION,
        )


def build_review_plan(state: WorkflowState, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    company = _company_name(state)
    if state.workflow_id == "growth_diagnostic_to_blueprint_lite":
        return _blueprint_lite_plan(company, output)
    if state.workflow_id == "discovery_evidence_to_growth_sprint_proposal":
        return _growth_sprint_plan(company, output)
    if state.workflow_id in {"growth_sprint_to_research_engine", "blueprint_lite_to_discovery_preparation"}:
        return _research_strategy_plan(company, output)
    if state.workflow_id == "research_to_growth_blueprint":
        return _growth_blueprint_plan(company, output)
    raise HumanReviewArtifactError(
        f"no human review presentation contract is registered for {state.workflow_id}"
    )


class NarratiiveReviewPDFRenderer:
    """Shared restrained editorial renderer for Narratiive review documents."""

    def render(self, plan: ReviewDocumentPlan) -> tuple[bytes, int]:
        descriptor, temporary = tempfile.mkstemp(prefix=".narratiive-review-", suffix=".pdf")
        os.close(descriptor)
        temporary_path = Path(temporary)
        try:
            document = _ReviewDocTemplate(temporary_path, plan)
            story = _story(plan, document.styles)
            document.build(story, canvasmaker=_InvariantCanvas)
            data = temporary_path.read_bytes()
            if not data.startswith(b"%PDF-"):
                raise HumanReviewArtifactError("review renderer did not produce a PDF")
            return data, document.page_count
        finally:
            temporary_path.unlink(missing_ok=True)


class _InvariantCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)


class _ReviewDocTemplate(BaseDocTemplate):
    def __init__(self, target: Path, plan: ReviewDocumentPlan) -> None:
        super().__init__(
            str(target),
            pagesize=A4,
            leftMargin=23 * mm,
            rightMargin=23 * mm,
            topMargin=23 * mm,
            bottomMargin=20 * mm,
            title=f"{plan.company} - {plan.product}",
            author="Narratiive",
            subject="Human review artefact",
        )
        width, height = A4
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            width - self.leftMargin - self.rightMargin,
            height - self.topMargin - self.bottomMargin,
            id="review",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="review", frames=(frame,), onPage=self._decorate))
        self.plan = plan
        self.styles = _styles()
        self.page_count = 0

    def afterPage(self) -> None:
        self.page_count = self.page

    def _decorate(self, canvas: Canvas, document: BaseDocTemplate) -> None:
        width, height = A4
        canvas.saveState()
        if document.page == 1:
            canvas.setFillColor(IVORY)
            canvas.rect(0, 0, width, height, stroke=0, fill=1)
            canvas.setFillColor(AMBER)
            canvas.rect(0, height - 7 * mm, width, 7 * mm, stroke=0, fill=1)
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(23 * mm, 19 * mm, "NARRATIIVE")
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(STONE)
            canvas.drawRightString(width - 23 * mm, 19 * mm, "INTERNAL REVIEW")
        else:
            canvas.setStrokeColor(PALE)
            canvas.setLineWidth(0.7)
            canvas.line(23 * mm, height - 15 * mm, width - 23 * mm, height - 15 * mm)
            canvas.setFillColor(STONE)
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.drawString(23 * mm, height - 11.5 * mm, "NARRATIIVE")
            canvas.setFont("Helvetica", 7.5)
            canvas.drawRightString(width - 23 * mm, height - 11.5 * mm, self.plan.company.upper())
            canvas.drawString(23 * mm, 11 * mm, self.plan.product)
            canvas.drawRightString(width - 23 * mm, 11 * mm, str(document.page))
        canvas.restoreState()


class _Rule(Flowable):
    def __init__(self, width: float, colour=AMBER, thickness: float = 2.0) -> None:
        super().__init__()
        self.width = width
        self.height = thickness
        self.colour = colour
        self.thickness = thickness

    def draw(self) -> None:
        self.canv.setStrokeColor(self.colour)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.width, 0)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "ReviewEyebrow", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8,
            leading=10, textColor=AMBER, spaceAfter=7 * mm, tracking=1.5, uppercase=True,
        ),
        "company": ParagraphStyle(
            "ReviewCompany", parent=base["Title"], fontName="Times-Bold", fontSize=29,
            leading=31, textColor=INK, spaceAfter=4 * mm,
        ),
        "cover_title": ParagraphStyle(
            "ReviewCoverTitle", parent=base["Title"], fontName="Helvetica", fontSize=20,
            leading=24, textColor=INK, spaceAfter=8 * mm,
        ),
        "cover_subtitle": ParagraphStyle(
            "ReviewCoverSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=11,
            leading=17, textColor=STONE, spaceAfter=6 * mm, maxWidth=125 * mm,
        ),
        "section_no": ParagraphStyle(
            "ReviewSectionNo", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.5,
            leading=9, textColor=AMBER, spaceAfter=2 * mm, keepWithNext=True,
        ),
        "heading": ParagraphStyle(
            "ReviewHeading", parent=base["Heading1"], fontName="Times-Bold", fontSize=22,
            leading=25, textColor=INK, spaceAfter=6 * mm, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ReviewBody", parent=base["BodyText"], fontName="Helvetica", fontSize=10.3,
            leading=15.2, textColor=INK, spaceAfter=4.2 * mm, allowWidows=0, allowOrphans=0,
        ),
        "bullet": ParagraphStyle(
            "ReviewBullet", parent=base["BodyText"], fontName="Helvetica", fontSize=9.8,
            leading=14.2, textColor=INK, leftIndent=5 * mm, firstLineIndent=-4 * mm,
            bulletIndent=0, spaceAfter=2.8 * mm,
        ),
        "card_title": ParagraphStyle(
            "ReviewCardTitle", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=10.5,
            leading=13, textColor=INK, spaceAfter=2.2 * mm,
        ),
        "card_body": ParagraphStyle(
            "ReviewCardBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9.2,
            leading=13.2, textColor=INK, leftIndent=4 * mm, firstLineIndent=-3 * mm,
            spaceAfter=1.8 * mm,
        ),
        "decision": ParagraphStyle(
            "ReviewDecision", parent=base["BodyText"], fontName="Times-Bold", fontSize=15,
            leading=20, textColor=INK,
        ),
        "small": ParagraphStyle(
            "ReviewSmall", parent=base["BodyText"], fontName="Helvetica", fontSize=8.2,
            leading=12, textColor=STONE,
        ),
    }


def _story(plan: ReviewDocumentPlan, styles: Mapping[str, ParagraphStyle]) -> list[Flowable]:
    usable_width = A4[0] - 46 * mm
    decision_box = Table(
        [[Paragraph(_p(plan.decision_prompt), styles["decision"])]],
        colWidths=(usable_width,),
        style=TableStyle(
            (
                ("BACKGROUND", (0, 0), (-1, -1), IVORY),
                ("BOX", (0, 0), (-1, -1), 0.8, AMBER),
                ("LEFTPADDING", (0, 0), (-1, -1), 9 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 8 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8 * mm),
            )
        ),
    )
    story: list[Flowable] = [
        Spacer(1, 32 * mm),
        Paragraph(_p(f"{plan.gate_label} / HUMAN REVIEW"), styles["eyebrow"]),
        Paragraph(_p(plan.company), styles["company"]),
        Paragraph(_p(plan.product), styles["cover_title"]),
        _Rule(36 * mm),
        Spacer(1, 8 * mm),
        Paragraph(_p(plan.subtitle), styles["cover_subtitle"]),
        Spacer(1, 43 * mm),
        Paragraph("Prepared by Narratiive", styles["small"]),
        Paragraph("Approval status: Pending", styles["small"]),
        PageBreak(),
    ]
    for index, section in enumerate(plan.sections, 1):
        story.extend(
            [
                Paragraph(f"{index:02d}", styles["section_no"]),
                Paragraph(_p(section.heading), styles["heading"]),
            ]
        )
        for paragraph in section.body:
            story.append(Paragraph(_p(paragraph), styles["body"]))
        for item in section.items:
            story.append(Paragraph(_p(item), styles["bullet"], bulletText="-"))
        for title, items in section.cards:
            story.append(Paragraph(_p(title), styles["card_title"]))
            story.extend(Paragraph(_p(item), styles["card_body"], bulletText="-") for item in items)
            story.append(Spacer(1, 3.5 * mm))
        story.append(Spacer(1, 5 * mm))
        if index < len(plan.sections):
            story.extend((_Rule(usable_width, PALE, 0.6), Spacer(1, 7 * mm)))
    story.extend(
        (
            PageBreak(),
            Spacer(1, 25 * mm),
            Paragraph("DECISION", styles["eyebrow"]),
            Paragraph("Your judgement is the next step", styles["heading"]),
            decision_box,
            Spacer(1, 7 * mm),
            Paragraph(_p(f"If approved: {plan.next_if_approved}"), styles["body"]),
            Spacer(1, 12 * mm),
            _Rule(36 * mm),
            Spacer(1, 7 * mm),
            Paragraph(
                "This review document is derived from Narratiive's authoritative source. "
                "It is not approved for client use or external circulation.",
                styles["small"],
            ),
        )
    )
    return story


def _growth_sprint_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    synthesis = _required_text(output, "discovery_synthesis")
    challenge = _required_text(output, "growth_problem_or_opportunity")
    justification = _required_text(output, "why_further_strategic_work_is_justified")
    scope = _text_list(output.get("proposed_scope"))
    workstreams = _workstream_cards(output.get("workstreams_and_questions"))
    deliverables = _text_list(output.get("expected_growth_blueprint_outputs"))
    commercial = output.get("commercial_proposal_inputs")
    if not isinstance(commercial, Mapping):
        raise HumanReviewArtifactError("Growth Sprint proposal is missing commercial inputs")
    timeline = _clean_text(commercial.get("timeline"))
    investment = _clean_text(commercial.get("investment_recommendation"))
    assumptions = _text_list(output.get("assumptions_and_dependencies"))
    question_count = sum(len(items) for _, items in workstreams)
    workstream_count = len(workstreams)
    decision = (
        f"Decide whether these {workstream_count} workstreams correctly define what Narratiive should solve "
        "before research and the Growth Blueprint begin. Approve the proposal, request revision, or identify the choice that needs to change."
    )
    focus = (
        challenge,
        f"The proposed Sprint is organised around {workstream_count} workstreams and {question_count} strategic questions.",
        f"Indicative timing: {timeline or 'To be confirmed through review.'}",
        f"Commercial status: {investment or 'Pending human review.'}",
    )
    sections = (
        ReviewSection("The situation / what we heard", body=(synthesis,)),
        ReviewSection("The growth challenge", body=(challenge,)),
        ReviewSection(
            "Our strategic hypothesis",
            body=(
                f"Our working hypothesis is that the opportunity is not solved by isolated messaging or channel optimisation. {challenge}",
            ),
        ),
        ReviewSection("Why this matters now", body=(justification,)),
        ReviewSection("What the Growth Sprint will answer", items=tuple(item for _, questions in workstreams for item in questions)),
        ReviewSection("Proposed workstreams", cards=workstreams, items=scope),
        ReviewSection("What the Growth Blueprint will deliver", items=deliverables),
        ReviewSection(
            "How the Sprint will work / indicative timing",
            body=(f"Indicative timing: {timeline or 'To be confirmed through review.'}",),
            items=(
                "Align the evidence and the decisions the work must unlock.",
                "Investigate the priority audience, category and positioning questions.",
                "Synthesize the evidence into a clear strategic thesis and Growth Blueprint.",
                "Return the exact strategic choices for human review before activation.",
            ),
        ),
        ReviewSection(
            "Investment / commercial status",
            body=(investment or "Investment remains to be confirmed through human review.", "Approval status: Pending."),
        ),
        ReviewSection("Key assumptions or evidence gaps", items=assumptions),
    )
    return ReviewDocumentPlan(
        product="Growth Sprint Proposal",
        gate_label="GATE 2",
        company=company,
        subtitle="A focused strategic engagement to resolve the choices that must precede research, positioning and the Narratiive Growth Blueprint.",
        sections=sections,
        focus_points=tuple(item for item in focus if item)[:4],
        decision_prompt=decision,
        next_if_approved="Tony will commission the approved research scope and move the work into the Growth Blueprint production sequence. No client contact or external release will occur.",
    )


def _blueprint_lite_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    diagnosis = _clean_text(output.get("central_diagnosis")) or _clean_text(output.get("blueprint_lite"))
    tension = _required_text(output, "growth_tension")
    opportunity = _required_text(output, "provisional_opportunity")
    evidence = tuple(_clean_text(item.get("fact") if isinstance(item, Mapping) else item) for item in output.get("source_backed_evidence", ()) if _clean_text(item.get("fact") if isinstance(item, Mapping) else item))
    gaps = _text_list(output.get("evidence_gaps"))
    questions = _text_list(output.get("questions_to_answer_next"))
    return ReviewDocumentPlan(
        product="Blueprint Lite",
        gate_label="GATE 1",
        company=company,
        subtitle="A concise strategic read on the current growth tension and the opportunity worth validating next.",
        sections=(
            ReviewSection("Executive read", body=(diagnosis,)),
            ReviewSection("The growth tension", body=(tension,)),
            ReviewSection("The provisional opportunity", body=(opportunity,)),
            ReviewSection("What supports this view", items=evidence),
            ReviewSection("What remains uncertain", items=gaps),
            ReviewSection("Questions for Discovery", items=questions),
        ),
        focus_points=(diagnosis, tension, opportunity)[:3],
        decision_prompt="Decide whether the diagnosis is strong and specific enough to progress into Discovery, or identify what should be revised first.",
        next_if_approved="Tony will prepare and conduct Discovery against the approved diagnosis. No client-facing output will be released without the relevant approval.",
    )


def _research_strategy_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    synthesis = (
        _clean_text(output.get("context_summary"))
        or _clean_text(output.get("consolidated_findings"))
        or _clean_text(output.get("strategy_thesis"))
    )
    if not synthesis:
        raise HumanReviewArtifactError("research or strategy review is missing a synthesis")
    tensions = _human_items(output.get("strategic_tensions"), preferred=("tension", "statement", "claim"))
    gaps = _text_list(output.get("knowledge_gaps")) or _text_list(output.get("research_gaps"))
    questions = _text_list(output.get("discovery_questions")) or _human_items(
        output.get("research_tasks"), preferred=("question", "task")
    )
    return ReviewDocumentPlan(
        product="Research and Strategy Review",
        gate_label="STRATEGY REVIEW",
        company=company,
        subtitle="The evidence, tensions and choices that should shape the next strategic decision.",
        sections=(
            ReviewSection("Executive synthesis", body=(synthesis,)),
            ReviewSection("Strategic tensions", items=tensions),
            ReviewSection("Questions the work must resolve", items=questions),
            ReviewSection("Material evidence gaps", items=gaps),
        ),
        focus_points=tuple(item for item in (synthesis, *tensions[:2]) if item)[:3],
        decision_prompt="Decide whether the evidence and strategic framing are sufficient to proceed, or identify the unresolved question that must be addressed first.",
        next_if_approved="Tony will advance only the approved strategic scope to the next registered workflow stage.",
    )


def _growth_blueprint_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    sections: list[ReviewSection] = []
    mapping = (
        ("market_category_diagnosis", "Market and category diagnosis"),
        ("audience", "Priority audience"),
        ("growth_barriers", "Growth barriers"),
        ("source_of_difference", "Source of difference"),
        ("positioning", "Positioning"),
        ("narrative", "Narrative platform"),
        ("growth_opportunity", "Growth opportunity"),
        ("activation_implications", "Activation implications"),
    )
    for key, heading in mapping:
        raw = output.get(key)
        if isinstance(raw, Mapping):
            body = tuple(
                text
                for text in (
                    _clean_text(raw.get("diagnosis")),
                    _clean_text(raw.get("implication")),
                )
                if text
            )
            uncertainty = _text_list(raw.get("uncertainties"))
            if body or uncertainty:
                sections.append(ReviewSection(heading, body=body, items=uncertainty))
    choices = _human_items(output.get("key_strategic_choices"), preferred=("choice", "decision"))
    uncertainty = _text_list(output.get("evidence_and_uncertainty"))
    if choices:
        sections.append(ReviewSection("The strategic choices", items=choices))
    if uncertainty:
        sections.append(ReviewSection("What remains uncertain", items=uncertainty))
    if not sections:
        raise HumanReviewArtifactError("Growth Blueprint review has no presentable strategic sections")
    focus = tuple(
        _clean_text((output.get(key) or {}).get("implication") if isinstance(output.get(key), Mapping) else "")
        for key in ("growth_opportunity", "positioning", "narrative")
    )
    return ReviewDocumentPlan(
        product="Narratiive Growth Blueprint",
        gate_label="PRODUCT REVIEW",
        company=company,
        subtitle="The strategic diagnosis, point of view and choices that will govern the next stage of growth.",
        sections=tuple(sections),
        focus_points=tuple(item for item in focus if item)[:3],
        decision_prompt="Decide whether the strategic thesis and choices are strong enough to progress into presentation production, or request a bounded revision.",
        next_if_approved="Tony will commission presentation production from this approved strategic source. Client release remains separately approval-gated.",
    )


def _produced_growth_blueprint_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    specification = output.get("presentation_specification")
    slides = specification.get("slides") if isinstance(specification, Mapping) else None
    focus: list[str] = []
    if isinstance(slides, Sequence) and not isinstance(slides, (str, bytes)):
        for slide in slides:
            if not isinstance(slide, Mapping):
                continue
            takeaway = _clean_text(slide.get("takeaway"))
            if takeaway and takeaway.casefold() not in {item.casefold() for item in focus}:
                focus.append(takeaway)
            if len(focus) == 4:
                break
    if not focus:
        focus.append("Review the strategic argument, narrative progression and activation choices in the attached Growth Blueprint.")
    return ReviewDocumentPlan(
        product="Narratiive Growth Blueprint",
        gate_label="PRODUCT GATE",
        company=company,
        subtitle="The complete presentation produced from the approved strategic source.",
        sections=(ReviewSection("Review focus", items=tuple(focus)),),
        focus_points=tuple(focus),
        decision_prompt="Decide whether the Growth Blueprint is ready for the next approved use, or identify the exact revision required.",
        next_if_approved="Tony will record the decision for this exact presentation version. Any client-facing release remains separately approval-gated.",
    )


def _telegram_notification(plan: ReviewDocumentPlan) -> str:
    decision = plan.decision_prompt.rstrip(".")
    if decision.casefold().startswith("decide whether "):
        decision = "whether " + decision[len("decide whether ") :]
    elif decision.casefold().startswith("decide "):
        decision = decision[len("decide ") :]
    return (
        f"{plan.gate_label.title()} is ready. I've emailed you the {plan.product} for review. "
        f"The main decision is {decision}."
    )[:900]


def _company_name(state: WorkflowState) -> str:
    payload = state.input_payload
    for value in (
        payload.get("company"),
        payload.get("company_name"),
        (payload.get("commercial_context") or {}).get("company") if isinstance(payload.get("commercial_context"), Mapping) else None,
        (payload.get("company_context") or {}).get("name") if isinstance(payload.get("company_context"), Mapping) else None,
        (payload.get("client_context") or {}).get("name") if isinstance(payload.get("client_context"), Mapping) else None,
    ):
        if _clean_text(value):
            return _clean_text(value)
    return state.entity_id or state.client_id


def _workstream_cards(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        title = _clean_text(item.get("workstream"))
        questions = _text_list(item.get("questions"))
        if title and questions:
            result.append((title, questions))
    return tuple(result)


def _human_items(value: Any, *, preferred: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            text = next((_clean_text(item.get(key)) for key in preferred if _clean_text(item.get(key))), "")
            implication = _clean_text(item.get("implication")) or _clean_text(item.get("tradeoff"))
            if text and implication:
                text = f"{text} - {implication}"
        else:
            text = _clean_text(item)
        if text:
            result.append(text)
    return tuple(result)


def _text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(text for item in value if (text := _clean_text(item)))


def _required_text(output: Mapping[str, Any], key: str) -> str:
    value = _clean_text(output.get(key))
    if not value:
        raise HumanReviewArtifactError(f"review source is missing {key}")
    return value


def _clean_text(value: Any) -> str:
    if value is None or isinstance(value, Mapping):
        return ""
    text = " ".join(str(value).split())
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(
        r"\b(?:ev[_-][A-Za-z0-9_-]+|artifact-[A-Za-z0-9_-]+|workflow[_-](?:run[_-])?[A-Za-z0-9_-]+|run-[0-9][A-Za-z0-9_-]*)\b",
        "",
        text,
        flags=re.I,
    )
    return " ".join(text.split()).strip(" ,;:-")


def _p(value: str) -> str:
    return escape(_clean_text(value)).replace("\n", "<br/>")


def _validate_review_plan(plan: ReviewDocumentPlan) -> None:
    visible = " ".join(
        (
            plan.product,
            plan.gate_label,
            plan.company,
            plan.subtitle,
            plan.decision_prompt,
            plan.next_if_approved,
            *plan.focus_points,
            *(section.heading for section in plan.sections),
            *(item for section in plan.sections for item in section.body),
            *(item for section in plan.sections for item in section.items),
            *(title for section in plan.sections for title, _ in section.cards),
            *(item for section in plan.sections for _, items in section.cards for item in items),
        )
    ).casefold()
    leaked = sorted(field for field in PROHIBITED_VISIBLE_FIELDS if field in visible)
    if leaked:
        raise HumanReviewArtifactError(
            "review presentation contains internal field names: " + ", ".join(leaked)
        )


def _safe_path_component(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text or text in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]+", text):
        raise HumanReviewArtifactError(f"invalid {field_name}")
    return text


def _safe_filename(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return "-".join(words)[:80] or "Narratiive-review"


def _persist_immutable(target: Path, content: bytes) -> None:
    if target.exists():
        if target.read_bytes() != content:
            raise HumanReviewArtifactError(f"immutable review artefact collision: {target.name}")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
