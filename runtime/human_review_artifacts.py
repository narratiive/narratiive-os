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
from dataclasses import asdict, dataclass, field
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
from runtime.fieldwork_proposal_pdf import (
    FieldworkProposalDraft,
    FieldworkProposalPDFRenderer,
    FieldworkProposalQualityGate,
    ProposalInsight,
)
from runtime.workflow_quality import validate_approved_fieldwork_fee


RENDERER_ID = "narratiive-human-review-pdf"
RENDERER_VERSION = "2"
FIELDWORK_PRESENTATION_RENDERER_ID = FieldworkProposalPDFRenderer.renderer_id
FIELDWORK_PRESENTATION_RENDERER_VERSION = FieldworkProposalPDFRenderer.renderer_version
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
    input_lineage: Mapping[str, str]
    evidence_record: Mapping[str, Any] = field(default_factory=dict)

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
        evidence_record: Mapping[str, Any] | None = None,
        input_lineage: Mapping[str, str] | None = None,
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
                    json.dumps(dict(evidence_record or {}), sort_keys=True, separators=(",", ":")),
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
            input_lineage=dict(input_lineage or {}),
            evidence_record=dict(evidence_record or {}),
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
        renderer_id = RENDERER_ID
        renderer_version = RENDERER_VERSION
        # The two-page FIELDWORK presentation is deliberately stricter than
        # the established internal-review renderer.  A current-shaped record
        # without an exact, append-only commercial approval remains an
        # internal review record; it must not be converted into a
        # client-language quotation simply because it has newer fields.
        fieldwork_presentation_ready = (
            state.workflow_id == "discovery_evidence_to_growth_sprint_proposal"
            and _is_current_fieldwork_presentation_source(output)
            and _has_source_bound_fieldwork_quality_assessment(state, source)
        )
        if fieldwork_presentation_ready:
            proposal = build_fieldwork_proposal_draft(state, source, output)
            pdf_bytes, pages = FieldworkProposalPDFRenderer()._render_validated(proposal)
            renderer_id = FIELDWORK_PRESENTATION_RENDERER_ID
            renderer_version = FIELDWORK_PRESENTATION_RENDERER_VERSION
        else:
            pdf_bytes, pages = NarratiiveReviewPDFRenderer().render(plan)
        return self.store.persist(
            state=state,
            source=source,
            plan=plan,
            pdf_bytes=pdf_bytes,
            page_count=pages,
            renderer_id=renderer_id,
            renderer_version=renderer_version,
            evidence_record=(
                {
                    **_fieldwork_presentation_evidence_record(output),
                    "visual_assets": list(proposal.asset_lineage()),
                }
                if fieldwork_presentation_ready
                else {}
            ),
            input_lineage=(
                _review_input_lineage(state, source)
                if fieldwork_presentation_ready and _has_bound_fieldwork_fee_approval(state, source)
                else {}
            ),
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
        if not isinstance(output.get("proposal_evidence_readiness"), Mapping) or not isinstance(output.get("fieldwork_offer"), Mapping):
            return _legacy_growth_sprint_plan(company, output)
        return _growth_sprint_plan(
            company,
            output,
            _fieldwork_fee_for_review(state.input_payload),
            _discovery_source_ids(state.input_payload),
        )
    if state.workflow_id in {
        "growth_sprint_to_research_engine",
        "blueprint_lite_to_discovery_preparation",
        "research_to_strategic_synthesis",
    }:
        return _research_strategy_plan(company, output)
    if state.workflow_id == "strategic_synthesis_to_strategy_thesis":
        return _strategy_thesis_plan(company, output)
    if state.workflow_id in {"research_to_growth_blueprint", "strategy_thesis_to_growth_blueprint"}:
        return _growth_blueprint_plan(company, output)
    raise HumanReviewArtifactError(
        f"no human review presentation contract is registered for {state.workflow_id}"
    )


def _legacy_growth_sprint_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    """Keep immutable pre-FIELDWORK-schema records readable and reviewable."""
    synthesis = _required_text(output, "discovery_synthesis")
    challenge = _required_text(output, "growth_problem_or_opportunity")
    scope = _text_list(output.get("proposed_scope"))
    deliverables = _text_list(output.get("expected_growth_blueprint_outputs"))
    assumptions = _text_list(output.get("assumptions_and_dependencies"))
    return ReviewDocumentPlan(
        product="Historical strategic proposal",
        gate_label="HISTORICAL REVIEW",
        company=company,
        subtitle="An immutable proposal record retained for audit and historic review; it is not a current FIELDWORK quotation.",
        sections=(
            ReviewSection("What the record says", body=(synthesis,)),
            ReviewSection("The opportunity considered", body=(challenge,)),
            ReviewSection("Scope recorded", items=scope),
            ReviewSection("Outputs recorded", items=deliverables),
            ReviewSection("Evidence limits", items=assumptions),
        ),
        focus_points=(challenge, *scope[:2]),
        decision_prompt="Review this historical record against its original context; it does not create a current client-facing action.",
        next_if_approved="No automatic action follows from a historical proposal record.",
    )


def _is_current_fieldwork_presentation_source(output: Mapping[str, Any]) -> bool:
    return isinstance(output.get("proposal_evidence_readiness"), Mapping) and isinstance(output.get("fieldwork_offer"), Mapping)


def _validate_authoritative_proposal_source(source: ArtifactRef, output: Mapping[str, Any]) -> None:
    """Require the supplied render data to be the exact persisted source bytes."""
    expected_checksum = str(source.checksum or "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_checksum):
        raise HumanReviewArtifactError("FIELDWORK presentation requires a checksummed authoritative proposal source")
    try:
        raw = Path(source.location).read_bytes()
        persisted = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HumanReviewArtifactError("FIELDWORK authoritative proposal source cannot be read") from exc
    if hashlib.sha256(raw).hexdigest() != expected_checksum:
        raise HumanReviewArtifactError("FIELDWORK authoritative proposal source checksum does not match")
    if not isinstance(persisted, Mapping) or persisted != output:
        raise HumanReviewArtifactError("FIELDWORK render input does not match the persisted authoritative proposal source")


def _fieldwork_quality_gate(state: WorkflowState, source: ArtifactRef) -> FieldworkProposalQualityGate:
    """Resolve specialist assessments from append-only workflow history.

    The exact checksummed records must be present in the workflow's durable
    approval history and bound to this workspace, client, run and proposal
    source. Source metadata is deliberately not consulted: it can become stale
    and must not select an earlier passing assessment over a later revision.
    """
    assessments: dict[str, Mapping[str, Any]] = {}
    for event in reversed(state.approval_history):
        if not isinstance(event, Mapping) or event.get("decision") != "fieldwork_presentation_quality_assessment":
            continue
        reviewer = str(event.get("reviewer") or "")
        if reviewer not in {"Strategy Director", "Creative Director"} or reviewer in assessments:
            continue
        if {
            "workspace_id": str(event.get("workspace_id") or ""),
            "client_id": str(event.get("client_id") or ""),
            "run_id": str(event.get("run_id") or ""),
            "source_artifact_checksum": str(event.get("source_artifact_checksum") or ""),
        } != {
            "workspace_id": state.workspace_id,
            "client_id": state.client_id,
            "run_id": state.run_id,
            "source_artifact_checksum": str(source.checksum or ""),
        }:
            continue
        _validate_quality_assessment_artifact(state, event)
        assessments[reviewer] = event
    if set(assessments) != {"Strategy Director", "Creative Director"}:
        raise HumanReviewArtifactError("FIELDWORK presentation quality assessments are not present in append-only workflow history")
    try:
        gate = FieldworkProposalQualityGate._from_append_only_history(
            strategy_director=assessments["Strategy Director"],
            creative_director=assessments["Creative Director"],
            source_artifact_checksum=str(source.checksum or ""),
        )
    except (KeyError, TypeError) as exc:
        raise HumanReviewArtifactError("FIELDWORK presentation quality assessments are incomplete") from exc
    try:
        gate.validate(str(source.checksum or ""))
    except Exception as exc:
        raise HumanReviewArtifactError(str(exc)) from exc
    return gate


def _validate_quality_assessment_artifact(state: WorkflowState, event: Mapping[str, Any]) -> None:
    """Verify a quality event names immutable, persisted assessment content."""
    artifact_id = str(event.get("assessment_artifact_id") or "")
    expected_checksum = str(event.get("assessment_artifact_checksum") or "")
    if not artifact_id or not re.fullmatch(r"[0-9a-f]{64}", expected_checksum):
        raise HumanReviewArtifactError("FIELDWORK quality assessment does not identify an immutable assessment artefact")
    candidates = [
        artifact
        for stage in state.stages
        for artifact in (*stage.input_artifacts, *stage.output_artifacts)
        if artifact.artifact_id == artifact_id
        and artifact.artifact_type == "fieldwork_presentation_quality_assessment"
    ]
    if len(candidates) != 1:
        raise HumanReviewArtifactError("FIELDWORK quality assessment artefact is not present in persisted workflow lineage")
    artifact = candidates[0]
    try:
        raw = Path(artifact.location).read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HumanReviewArtifactError("FIELDWORK quality assessment artefact cannot be read") from exc
    if hashlib.sha256(raw).hexdigest() != expected_checksum or artifact.checksum != expected_checksum:
        raise HumanReviewArtifactError("FIELDWORK quality assessment artefact checksum does not match history")
    expected_payload = {
        key: event.get(key)
        for key in (
            "reviewer", "assessment_artifact_id", "recorded_at",
            "source_artifact_checksum", "criteria", "assessment_checksum",
        )
    }
    if payload != expected_payload:
        raise HumanReviewArtifactError("FIELDWORK quality assessment artefact does not match its append-only history record")


def _has_source_bound_fieldwork_quality_assessment(state: WorkflowState, source: ArtifactRef) -> bool:
    try:
        _fieldwork_quality_gate(state, source)
    except HumanReviewArtifactError:
        return False
    return True


def _has_bound_fieldwork_fee_approval(state: WorkflowState, source: ArtifactRef) -> bool:
    """Return whether this exact source has a durable commercial approval.

    This is intentionally a predicate for renderer selection rather than an
    exception: historic/internal review artefacts must remain readable even
    where their original fee record predates the source-bound FIELDWORK
    presentation contract.
    """
    try:
        _bound_fieldwork_fee_approval(state, source)
    except HumanReviewArtifactError:
        return False
    return True


def _bound_fieldwork_fee_approval(state: WorkflowState, source: ArtifactRef) -> Mapping[str, Any]:
    """Validate the exact approval required for a client-language proposal."""
    context = state.input_payload.get("commercial_context")
    fee_input = context.get("approved_fieldwork_fee") if isinstance(context, Mapping) else None
    try:
        validated_fee = validate_approved_fieldwork_fee(fee_input)
    except ValueError as exc:
        raise HumanReviewArtifactError(str(exc)) from exc

    reference = validated_fee["approval_reference"]
    binding = {
        "workspace_id": str(reference.get("workspace_id") or ""),
        "client_id": str(reference.get("client_id") or ""),
        "run_id": str(reference.get("run_id") or ""),
        "source_artifact_checksum": str(reference.get("source_artifact_checksum") or ""),
    }
    if binding != {
        "workspace_id": state.workspace_id,
        "client_id": state.client_id,
        "run_id": state.run_id,
        "source_artifact_checksum": str(source.checksum or ""),
    }:
        raise HumanReviewArtifactError("FIELDWORK fee approval is not bound to this workspace, client, run and source artefact")

    approval_id = str(reference["approval_id"])
    if not any(
        item.get("approval_id") == approval_id
        and item.get("decision") == "approved_fieldwork_fee"
        and item.get("fee_checksum") == reference["fee_checksum"]
        and item.get("source_artifact_checksum") == source.checksum
        for item in state.approval_history
        if isinstance(item, Mapping)
    ):
        raise HumanReviewArtifactError("FIELDWORK fee approval is not present in append-only approval history")
    return validated_fee


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


def _growth_sprint_plan(
    company: str,
    output: Mapping[str, Any],
    approved_fee: str,
    discovery_source_ids: frozenset[str],
) -> ReviewDocumentPlan:
    synthesis = _required_text(output, "discovery_synthesis")
    challenge = _required_text(output, "growth_problem_or_opportunity")
    opportunity = output.get("commercial_opportunity") if isinstance(output.get("commercial_opportunity"), Mapping) else {}
    commercial_read = _commercial_read_cards(output.get("commercial_read"))
    hypothesis = output.get("strategic_hypothesis") if isinstance(output.get("strategic_hypothesis"), Mapping) else {}
    offer = output.get("fieldwork_offer") if isinstance(output.get("fieldwork_offer"), Mapping) else {}
    editorial_plan = output.get("editorial_plan") if isinstance(output.get("editorial_plan"), Mapping) else {}
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
    recommendation = _clean_text(offer.get("recommendation"))
    duration = _clean_text(offer.get("duration")) or timeline
    investment_status = _clean_text(offer.get("investment_status")) or investment
    deliverables = _text_list(offer.get("deliverables")) or deliverables
    argument = _text_list(editorial_plan.get("argument"))
    decision = "Approve this exact FIELDWORK proposal, request a revision, or identify the commercial or strategic choice that must change."
    focus = (
        _clean_text(opportunity.get("headline")) or _clean_text(hypothesis.get("commercial_tension")) or challenge,
        _clean_text(hypothesis.get("decision_fieldwork_will_unlock")),
        f"Indicative duration: {duration or 'To be confirmed through review.'}",
        f"Investment status: {investment_status or 'Pending human review.'}",
    )
    sections = (
        ReviewSection(
            "The opportunity",
            body=tuple(
                item for item in (
                    _clean_text(opportunity.get("headline")),
                    _clean_text(opportunity.get("commercial_insight")),
                    _monetary_estimate_text(opportunity.get("monetary_estimate"), discovery_source_ids),
                ) if item
            ),
        ),
        ReviewSection("What we heard", body=(synthesis,)),
        ReviewSection("The opportunity worth taking seriously", body=(_clean_text(hypothesis.get("commercial_tension")) or challenge,)),
        ReviewSection("What the evidence suggests", cards=commercial_read),
        ReviewSection(
            "Our point of view",
            body=tuple(
                item for item in (
                    _clean_text(hypothesis.get("what_may_be_overlooked")),
                    _clean_text(hypothesis.get("why_conventional_approach_is_insufficient")),
                ) if item
            ),
        ),
        ReviewSection("What becomes possible", body=(justification,)),
        ReviewSection("The decisions FIELDWORK will unlock", body=tuple(argument[3:6]), items=tuple(item for _, questions in workstreams for item in questions)),
        ReviewSection("Introducing FIELDWORK", body=(recommendation,), cards=workstreams, items=scope),
        ReviewSection("What you will receive", items=deliverables),
        ReviewSection("How we will work together", body=(f"Indicative duration: {duration or 'To be confirmed through review.'}",), items=("Align on the commercial decisions this work must resolve.", "Investigate the audience, category and positioning questions that matter most.", "Return a strategic recommendation with clear choices and next steps.")),
        ReviewSection("Investment", body=(approved_fee,)),
        ReviewSection("Evidence boundaries", items=assumptions),
    )
    return ReviewDocumentPlan(
        product="Narratiive FIELDWORK Proposal",
        gate_label="FOUNDER REVIEW",
        company=company,
        subtitle="A commercially focused strategic engagement, grounded in Discovery evidence and designed to resolve the decisions that matter most.",
        sections=sections,
        focus_points=tuple(item for item in focus if item)[:4],
        decision_prompt=decision,
        next_if_approved="Tony will commission the approved FIELDWORK scope through the existing governed research and strategy sequence. No client contact or external release will occur.",
    )


def build_fieldwork_proposal_draft(
    state: WorkflowState,
    source: ArtifactRef,
    output: Mapping[str, Any],
) -> FieldworkProposalDraft:
    """Create the fixed client-language presentation only when source is ready.

    The structured proposal stays authoritative.  This adapter deliberately
    refuses unresolved evidence and unapproved commercial terms rather than
    disguising them in a handsome PDF.
    """
    _validate_authoritative_proposal_source(source, output)
    readiness = output.get("proposal_evidence_readiness")
    if not isinstance(readiness, Mapping) or readiness.get("client_facing_ready") is not True:
        raise HumanReviewArtifactError("FIELDWORK client presentation requires evidence approved for client-facing use")
    offer = output.get("fieldwork_offer")
    opportunity = output.get("commercial_opportunity")
    if not isinstance(offer, Mapping) or not isinstance(opportunity, Mapping):
        raise HumanReviewArtifactError("FIELDWORK client presentation is missing proposal source content")
    context = state.input_payload.get("commercial_context")
    fee_input = context.get("approved_fieldwork_fee") if isinstance(context, Mapping) else None
    if fee_input is None:
        fee = None
        approval_id = None
        fee_checksum = None
    else:
        validated_fee = _bound_fieldwork_fee_approval(state, source)
        amount = validated_fee["amount"]
        currency = _clean_text(validated_fee["currency"]).upper()
        display_amount = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
        fee = f"£{display_amount}" if currency == "GBP" else f"{currency} {display_amount}"
        reference = validated_fee["approval_reference"]
        approval_id = str(reference["approval_id"])
        fee_checksum = str(reference["fee_checksum"])
    read = _source_backed_commercial_read_cards(
        output.get("commercial_read"),
        allowed_source_ids=_fieldwork_presentation_source_ids(state),
    )
    source_insights = tuple(
        ProposalInsight(title=title, body=" ".join(items))
        for title, items in read[:3]
    )

    if len(source_insights) < 3:
        raise HumanReviewArtifactError("FIELDWORK presentation requires three substantive, source-backed strategic insights")
    deliverable_names = _text_list(offer.get("deliverables"))
    if len(deliverable_names) < 3:
        raise HumanReviewArtifactError("FIELDWORK client presentation requires three deliverables")
    deliverables = tuple(
        ProposalInsight(
            title=name,
            body=(
                "A focused, practical output shaped around the commercial decisions that matter most."
            ),
        )
        for name in deliverable_names[:3]
    )
    estimate = opportunity.get("monetary_estimate")
    metric_label = metric_value = metric_basis = None
    if isinstance(estimate, Mapping):
        metric_basis = _monetary_estimate_text(estimate, _discovery_source_ids(state.input_payload))
        amount = estimate.get("amount")
        currency = _clean_text(estimate.get("currency")).upper()
        if isinstance(amount, (int, float)) and not isinstance(amount, bool):
            display = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
            metric_value = f"£{display}" if currency == "GBP" else f"{currency} {display}"
            metric_label = "ILLUSTRATIVE COMMERCIAL OPPORTUNITY"
    return FieldworkProposalDraft(
        company=_company_name(state),
        headline=_clean_text(opportunity.get("headline")),
        introduction=_clean_text(output.get("growth_problem_or_opportunity")),
        opportunity_heading="A realistic path to more valuable demand.",
        opportunity_body=_clean_text(opportunity.get("commercial_insight")),
        opportunity_metric_label=metric_label,
        opportunity_metric_value=metric_value,
        opportunity_metric_basis=metric_basis,
        insights=(source_insights[0], source_insights[1], source_insights[2]),
        deliverables=(deliverables[0], deliverables[1], deliverables[2]),
        closing_headline="Make the next commercial choice with confidence.",
        closing_body="FIELDWORK brings together the evidence, choices and action plan needed to move forward with clarity.",
        timeline=_clean_text(offer.get("duration")),
        investment=fee,
        focus=_clean_text((output.get("strategic_hypothesis") or {}).get("decision_fieldwork_will_unlock") if isinstance(output.get("strategic_hypothesis"), Mapping) else ""),
        internal_review_only=True,
        verified_fee_binding=(
            {"approval_id": approval_id, "fee_checksum": fee_checksum}
            if approval_id and fee_checksum else None
        ),
        source_summary=_clean_text(opportunity.get("basis")),
        quality_gate=_fieldwork_quality_gate(state, source),
        source_artifact_checksum=str(source.checksum or ""),
    )


def _fieldwork_presentation_evidence_record(output: Mapping[str, Any]) -> Mapping[str, Any]:
    """Persist required evidence context backstage, never in the visible PDF."""
    opportunity = output.get("commercial_opportunity")
    readiness = output.get("proposal_evidence_readiness")
    estimate = opportunity.get("monetary_estimate") if isinstance(opportunity, Mapping) else None
    return {
        "opportunity": {
            "classification": _clean_text(opportunity.get("classification")) if isinstance(opportunity, Mapping) else "",
            "confidence": "not independently scored; use the claim classification and listed limitations",
            "source_refs": list(opportunity.get("evidence_refs") or ()) if isinstance(opportunity, Mapping) else [],
            "basis": _clean_text(opportunity.get("basis")) if isinstance(opportunity, Mapping) else "",
            "monetary_estimate": dict(estimate) if isinstance(estimate, Mapping) else None,
        },
        "assumptions": list(_text_list(output.get("assumptions_and_dependencies"))),
        "limitations": {
            "material_contradictions": list(readiness.get("material_contradictions") or ()) if isinstance(readiness, Mapping) else [],
            "missing_evidence": list(readiness.get("missing_evidence") or ()) if isinstance(readiness, Mapping) else [],
            "required_clarification": list(readiness.get("required_clarification") or ()) if isinstance(readiness, Mapping) else [],
        },
    }


def _approved_fieldwork_fee(payload: Mapping[str, Any]) -> str:
    context = payload.get("commercial_context")
    fee = context.get("approved_fieldwork_fee") if isinstance(context, Mapping) else None
    try:
        validated = validate_approved_fieldwork_fee(fee)
    except ValueError as exc:
        raise HumanReviewArtifactError(str(exc)) from exc
    amount = validated.get("amount")
    currency = _clean_text(validated.get("currency")).upper()
    formatted = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
    display = f"£{formatted}" if currency == "GBP" else f"{currency} {formatted}"
    return f"FIELDWORK fee: {display}"


def _fieldwork_fee_for_review(payload: Mapping[str, Any]) -> str:
    """Internal review may name a missing fee; it must never invent one."""
    context = payload.get("commercial_context")
    fee = context.get("approved_fieldwork_fee") if isinstance(context, Mapping) else None
    if fee is None:
        return "FIELDWORK investment: to be agreed before any client quotation."
    return _approved_fieldwork_fee(payload)


def _monetary_estimate_text(value: Any, discovery_source_ids: frozenset[str]) -> str:
    if not isinstance(value, Mapping):
        return ""
    amount = value.get("amount")
    currency = _clean_text(value.get("currency")).upper()
    basis = _clean_text(value.get("basis"))
    refs = value.get("evidence_refs")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0 or len(currency) != 3 or not basis:
        raise HumanReviewArtifactError("monetary opportunity is incomplete")
    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref in discovery_source_ids for ref in refs):
        raise HumanReviewArtifactError("monetary opportunity must reference supplied Discovery evidence")
    formatted = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
    display = f"£{formatted}" if currency == "GBP" else f"{currency} {formatted}"
    return f"Illustrative commercial opportunity: {display}. Basis: {basis}"


def _discovery_source_ids(payload: Mapping[str, Any]) -> frozenset[str]:
    evidence = payload.get("discovery_evidence")
    sources = evidence.get("sources") if isinstance(evidence, Mapping) else None
    if not isinstance(sources, list):
        return frozenset()
    return frozenset(
        str(source.get("source_id") or "").strip()
        for source in sources
        if isinstance(source, Mapping) and str(source.get("source_id") or "").strip()
    )


def _review_input_lineage(state: WorkflowState, source: ArtifactRef) -> Mapping[str, str]:
    """Lineage visible in a new FIELDWORK presentation's immutable manifest."""
    if state.workflow_id != "discovery_evidence_to_growth_sprint_proposal":
        return {}
    validated = _bound_fieldwork_fee_approval(state, source)
    reference = validated["approval_reference"]
    return {
        "fieldwork_fee_approval_id": str(reference["approval_id"]),
        "fieldwork_fee_checksum": str(reference["fee_checksum"]),
    }


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
        or _clean_text(
            output["strategic_synthesis"].get("executive_synthesis")
            if isinstance(output.get("strategic_synthesis"), Mapping)
            else ""
        )
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


def _strategy_thesis_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    thesis = output.get("strategy_thesis")
    if not isinstance(thesis, Mapping):
        raise HumanReviewArtifactError("Strategy Thesis review is missing the structured thesis")
    statement = _required_text(thesis, "thesis_statement")
    choices = _human_items(output.get("strategic_choices"), preferred=("choice",))
    uncertainty = _text_list(output.get("evidence_and_uncertainty"))
    decisions = _human_items(output.get("decision_register"), preferred=("decision",))
    return ReviewDocumentPlan(
        product="Strategy Thesis",
        gate_label="GATE 3",
        company=company,
        subtitle="The evidence-led strategic choices that will control the Narratiive Growth Blueprint.",
        sections=(
            ReviewSection("The thesis", body=(statement,)),
            ReviewSection("Commercial ambition", body=(_required_text(thesis, "commercial_ambition"),)),
            ReviewSection("Growth equation", body=(_required_text(thesis, "growth_equation"),)),
            ReviewSection("Priority audience", body=(_required_text(thesis, "priority_audience"),)),
            ReviewSection("Positioning and narrative", body=(
                _required_text(thesis, "positioning_choice"),
                _required_text(thesis, "narrative_platform"),
            )),
            ReviewSection("Strategic choices and trade-offs", items=choices),
            ReviewSection("Decisions requiring Matt", items=decisions),
            ReviewSection("Evidence limits and uncertainty", items=uncertainty),
        ),
        focus_points=(statement, *choices[:2]),
        decision_prompt="Approve this exact Strategy Thesis for Growth Blueprint production, request a revision, or identify the evidence question that must be resolved first.",
        next_if_approved="Tony will commission the Growth Blueprint from this exact approved thesis and its evidence lineage. No client release or external action will occur.",
    )


def _growth_blueprint_plan(company: str, output: Mapping[str, Any]) -> ReviewDocumentPlan:
    directed = output.get("client_facing_blueprint")
    if isinstance(directed, Mapping) and isinstance(directed.get("pages"), list):
        pages = [page for page in directed["pages"] if isinstance(page, Mapping)]
        sections = tuple(
            ReviewSection(
                _clean_text(page.get("headline")) or f"Page {page.get('page_number')}",
                body=tuple(
                    item for item in (
                        _clean_text(page.get("body")),
                        _clean_text(page.get("commercial_consequence")),
                    ) if item
                ),
            )
            for page in pages
        )
        if not sections:
            raise HumanReviewArtifactError("Growth Blueprint review has no presentable pages")
        return ReviewDocumentPlan(
            product="Narratiive Growth Blueprint",
            gate_label="PRODUCT REVIEW",
            company=company,
            subtitle=_clean_text(directed.get("central_argument")),
            sections=sections,
            focus_points=tuple(_clean_text(page.get("headline")) for page in pages[:3]),
            decision_prompt="Decide whether the finished strategic product is ready for the next approved use, or request a bounded revision.",
            next_if_approved="Tony will commission presentation production from this exact approved Blueprint Director version. Client release remains separately approval-gated.",
        )
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


def _commercial_read_cards(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Keep provenance backstage while presenting the commercial implication."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        observation = _clean_text(item.get("observation"))
        implication = _clean_text(item.get("commercial_implication"))
        classification = _clean_text(item.get("classification"))
        if observation and implication:
            label = _clean_text(item.get("title")) or (classification.title() if classification else "Commercial read")
            result.append((label, (observation, implication)))
    return tuple(result)


def _fieldwork_presentation_source_ids(state: WorkflowState) -> frozenset[str]:
    """Return the exact source identifiers a current presentation may cite.

    The PDF is a presentation of the canonical proposal evidence, not a place
    to introduce a plausible-looking insight with an invented provenance.
    """
    identifiers: set[str] = set()
    eligible_types = {
        "blueprint_lite", "discovery_evidence", "discovery_transcript",
        "groundwork", "research_evidence", "research_pack",
    }
    for stage in state.stages:
        for artifact in (*stage.input_artifacts, *stage.output_artifacts):
            if artifact.artifact_type not in eligible_types:
                continue
            identifiers.add(artifact.artifact_id)
    return frozenset(identifiers)


def _source_backed_commercial_read_cards(
    value: Any,
    *,
    allowed_source_ids: frozenset[str],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Accept only substantive insight cards with declared, in-scope evidence."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        observation = _clean_text(item.get("observation"))
        implication = _clean_text(item.get("commercial_implication"))
        classification = _clean_text(item.get("classification"))
        label = _clean_text(item.get("title")) or (classification.title() if classification else "")
        references = item.get("evidence_refs")
        refs = tuple(
            ref.strip() for ref in references
            if isinstance(ref, str) and ref.strip()
        ) if isinstance(references, Sequence) and not isinstance(references, (str, bytes)) else ()
        if not (label and observation and implication and refs):
            raise HumanReviewArtifactError("FIELDWORK strategic insights require a title, observation, commercial implication and evidence reference")
        if not allowed_source_ids or any(ref not in allowed_source_ids for ref in refs):
            raise HumanReviewArtifactError("FIELDWORK strategic insight cites evidence outside the authoritative Discovery or GROUNDWORK lineage")
        result.append((label, (observation, implication)))
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
