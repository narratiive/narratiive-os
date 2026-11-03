"""Two-page, evidence-bound FIELDWORK proposal presentation.

This is deliberately a renderer, not a second workflow.  It turns the
canonical proposal output into an immutable *review* presentation and leaves
the structured source, approval record and external-action gates untouched.
"""

from __future__ import annotations

import os
import re
import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


IVORY = colors.HexColor("#F5F0E6")
FOREST = colors.HexColor("#102D25")
COPPER = colors.HexColor("#B97835")
INK = colors.HexColor("#12231E")
MUTED = colors.HexColor("#625F58")
RULE = colors.HexColor("#B8B1A4")


class FieldworkProposalRenderError(ValueError):
    pass


_HISTORY_RESOLUTION_SEAL = object()


@dataclass(frozen=True, slots=True)
class ProposalInsight:
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class FieldworkProposalQualityGate:
    """Two specialist checks required before a proposal can be rendered.

    The checks are deliberately explicit.  They do not grant release approval:
    they prevent a generic or visually unfinished draft from being mistaken for
    a founder-review proposal.
    """

    strategy_director: Mapping[str, Any]
    creative_director: Mapping[str, Any]
    source_artifact_checksum: str
    _history_resolution: object | None = field(default=None, repr=False, compare=False)

    @classmethod
    def _from_append_only_history(
        cls,
        *,
        strategy_director: Mapping[str, Any],
        creative_director: Mapping[str, Any],
        source_artifact_checksum: str,
    ) -> "FieldworkProposalQualityGate":
        """Construct a gate only after runtime history has resolved both records."""
        return cls(
            strategy_director=strategy_director,
            creative_director=creative_director,
            source_artifact_checksum=source_artifact_checksum,
            _history_resolution=_HISTORY_RESOLUTION_SEAL,
        )

    def validate(self, expected_source_checksum: str) -> None:
        if self._history_resolution is not _HISTORY_RESOLUTION_SEAL:
            raise FieldworkProposalRenderError("FIELDWORK quality gate was not resolved from append-only workflow history")
        required_strategy = {
            "business_specificity",
            "commercial_relevance",
            "evidence_quality",
            "insight_distinctiveness",
            "commercial_proposition",
        }
        required_creative = {
            "headline_quality",
            "copywriting",
            "visual_hierarchy",
            "brand_expression",
            "editorial_quality",
        }
        for label, assessment, required in (
            ("Strategy Director", self.strategy_director, required_strategy),
            ("Creative Director", self.creative_director, required_creative),
        ):
            if not isinstance(assessment, Mapping):
                raise FieldworkProposalRenderError(f"{label} quality gate has not passed")
            reviewer = assessment.get("reviewer")
            assessment_id = assessment.get("assessment_artifact_id")
            recorded_at = assessment.get("recorded_at")
            bound_source = assessment.get("source_artifact_checksum")
            criteria = assessment.get("criteria")
            declared_checksum = assessment.get("assessment_checksum")
            if (
                reviewer != label
                or not isinstance(assessment_id, str) or not assessment_id.strip()
                or not isinstance(recorded_at, str) or not recorded_at.strip()
                or bound_source != expected_source_checksum
                or not isinstance(criteria, Mapping)
                or set(criteria) != required
                or any(value != "pass" for value in criteria.values())
                or not isinstance(declared_checksum, str)
            ):
                raise FieldworkProposalRenderError(f"{label} quality gate has not passed")
            record = {
                "reviewer": reviewer,
                "assessment_artifact_id": assessment_id,
                "recorded_at": recorded_at,
                "source_artifact_checksum": bound_source,
                "criteria": dict(criteria),
            }
            expected_assessment_checksum = hashlib.sha256(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if declared_checksum != expected_assessment_checksum:
                raise FieldworkProposalRenderError(f"{label} quality assessment checksum is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_artifact_checksum) or self.source_artifact_checksum != expected_source_checksum:
            raise FieldworkProposalRenderError("proposal quality gate is not bound to the rendered source artefact")


@dataclass(frozen=True, slots=True)
class VisualAssetRef:
    """A display asset with sufficient lineage for an immutable review record."""

    path: str
    source_id: str
    source_checksum: str
    origin_checksum: str
    rights: str
    transform: str

    def validate(self) -> None:
        if not all((self.path.strip(), self.source_id.strip(), self.source_checksum.strip(), self.origin_checksum.strip(), self.rights.strip(), self.transform.strip())):
            raise FieldworkProposalRenderError("visual assets require path, source, checksum, rights and transform lineage")
        source = Path(self.path)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != self.source_checksum:
            raise FieldworkProposalRenderError("visual asset bytes do not match the declared lineage checksum")


@dataclass(frozen=True, slots=True)
class FieldworkProposalDraft:
    """The small, client-language contract for the fixed two-page layout."""

    company: str
    headline: str
    introduction: str
    opportunity_heading: str
    opportunity_body: str
    opportunity_metric_label: str | None
    opportunity_metric_value: str | None
    opportunity_metric_basis: str | None
    insights: tuple[ProposalInsight, ProposalInsight, ProposalInsight]
    deliverables: tuple[ProposalInsight, ProposalInsight, ProposalInsight]
    closing_headline: str
    closing_body: str
    timeline: str
    investment: str | None
    focus: str
    hero_image: VisualAssetRef | None = None
    insight_images: tuple[VisualAssetRef | None, VisualAssetRef | None, VisualAssetRef | None] = (None, None, None)
    banner_image: VisualAssetRef | None = None
    internal_review_only: bool = True
    verified_fee_binding: Mapping[str, str] | None = None
    source_summary: str = ""
    quality_gate: FieldworkProposalQualityGate | None = None
    source_artifact_checksum: str = ""

    def validate(self) -> None:
        required = (self.company, self.headline, self.introduction, self.opportunity_heading,
                    self.opportunity_body, self.closing_headline, self.closing_body,
                    self.timeline, self.focus)
        if not all(str(item).strip() for item in required):
            raise FieldworkProposalRenderError("proposal draft is missing a required presentation field")
        if len(self.insights) != 3 or len(self.deliverables) != 3:
            raise FieldworkProposalRenderError("FIELDWORK proposal requires exactly three insights and deliverables")
        if self.quality_gate is None:
            raise FieldworkProposalRenderError("FIELDWORK proposal requires Strategy Director and Creative Director quality gates")
        self.quality_gate.validate(self.source_artifact_checksum)
        # This renderer deliberately creates immutable founder-review PDFs
        # only.  Client release remains a separately governed external action;
        # a bare Draft must never be able to assert an approval by supplying
        # values that merely look like a fee binding.
        if not self.internal_review_only:
            raise FieldworkProposalRenderError(
                "FIELDWORK proposal renderer is review-only; client release requires the governed external-action path"
            )
        if self.investment and not _valid_fee_binding(self.verified_fee_binding):
            raise FieldworkProposalRenderError("FIELDWORK investment requires a verified exact-fee binding")
        if bool(self.opportunity_metric_label) != bool(self.opportunity_metric_value):
            raise FieldworkProposalRenderError("opportunity metric label and value must be supplied together")
        visible = " ".join((self.headline, self.introduction, self.opportunity_heading, self.opportunity_body,
                            self.closing_headline, self.closing_body, self.timeline, self.investment or "", self.focus,
                            *(f"{item.title} {item.body}" for item in self.insights),
                            *(f"{item.title} {item.body}" for item in self.deliverables)))
        _validate_client_language(visible)
        _validate_editorial_specificity(self, visible)
        for asset in (self.hero_image, *self.insight_images, self.banner_image):
            if asset is not None:
                asset.validate()

    def asset_lineage(self) -> tuple[dict[str, str], ...]:
        records = []
        for role, asset in (("hero", self.hero_image), *( (f"insight_{index}", item) for index, item in enumerate(self.insight_images, 1) ), ("banner", self.banner_image)):
            if asset is not None:
                records.append({"role": role, "source_id": asset.source_id, "source_checksum": asset.source_checksum, "origin_checksum": asset.origin_checksum, "rights": asset.rights, "transform": asset.transform})
        return tuple(records)


def _font_names() -> tuple[str, str]:
    """Built-in PDF fonts keep the immutable render byte-stable across hosts."""
    return "Times-Roman", "Helvetica"


class FieldworkProposalPDFRenderer:
    """Print-quality A4 presentation with fixed hierarchy and bounded copy."""

    renderer_id = "narratiive-fieldwork-proposal-pdf"
    renderer_version = "2"

    def render(self, draft: FieldworkProposalDraft) -> tuple[bytes, int]:
        """Reject ungoverned rendering; use the authoritative review service."""
        raise FieldworkProposalRenderError(
            "FIELDWORK PDF rendering requires the authoritative HumanReviewPresentationService"
        )

    def _render_validated(self, draft: FieldworkProposalDraft) -> tuple[bytes, int]:
        """Render a draft only after the presentation service has verified lineage."""
        draft.validate()
        handle, name = tempfile.mkstemp(prefix=".narratiive-fieldwork-", suffix=".pdf")
        os.close(handle)
        target = Path(name)
        try:
            page_w, page_h = A4
            canvas = Canvas(str(target), pagesize=A4, invariant=1,
                            title=f"{draft.company} — FIELDWORK Proposal", author="Narratiive")
            canvas.setTitle(f"{draft.company} — FIELDWORK Proposal")
            canvas.setAuthor("Narratiive")
            serif, sans = _font_names()
            self._page_one(canvas, page_w, page_h, serif, sans, draft)
            canvas.showPage()
            self._page_two(canvas, page_w, page_h, serif, sans, draft)
            canvas.save()
            result = target.read_bytes()
            if not result.startswith(b"%PDF-"):
                raise FieldworkProposalRenderError("FIELDWORK renderer did not produce a PDF")
            return result, 2
        finally:
            target.unlink(missing_ok=True)

    def _base(self, c: Canvas, width: float, height: float, sans: str) -> None:
        c.setFillColor(IVORY)
        c.rect(0, 0, width, height, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont(sans, 8)
        c.drawString(31, height - 31, "N A R R A T I I V E")
        c.setFont(sans, 5.7)
        c.drawString(31, height - 42, "S T R A T E G Y   /   C R E A T I V E   /   G R O W T H")

    def _page_one(self, c: Canvas, w: float, h: float, serif: str, sans: str, d: FieldworkProposalDraft) -> None:
        self._base(c, w, h, sans)
        c.setFillColor(COPPER); c.setFont(sans, 7.6); c.drawString(33, h - 90, _caps(d.company))
        c.setStrokeColor(COPPER); c.setLineWidth(1.2); c.line(33, h - 100, 56, h - 100)
        c.setFillColor(INK); c.setFont(serif, 31)
        self._draw_wrapped(c, d.headline, 33, h - 120, 225, 37, 3, serif)
        c.setFillColor(INK); c.setFont(sans, 8.7)
        self._draw_wrapped(c, d.introduction, 33, h - 300, 222, 13, 5, sans)
        self._draw_image_or_panel(c, d.hero_image, 284, h - 382, 281, 382, FOREST, "")
        # Opportunity panel
        c.setFillColor(FOREST); c.rect(0, 275, w, 178, stroke=0, fill=1)
        c.setFillColor(colors.white); c.setFont(sans, 6.7); c.drawString(33, 427, "T H E   O P P O R T U N I T Y")
        c.setFont(serif, 22); self._draw_wrapped(c, d.opportunity_heading, 33, 408, 245, 27, 3, serif)
        c.setFont(sans, 7.7); self._draw_wrapped(c, d.opportunity_body, 33, 338, 244, 10.8, 5, sans)
        c.setStrokeColor(colors.HexColor("#6A817A")); c.line(326, 295, 326, 429)
        c.setFillColor(colors.white); c.setFont(sans, 6.5); c.drawString(347, 424, _caps(d.opportunity_metric_label or "COMMERCIAL OPPORTUNITY"))
        c.setFillColor(COPPER); c.setFont(serif, 15 if not d.opportunity_metric_value else 29)
        c.drawString(347, 383, d.opportunity_metric_value or "No quantified opportunity stated")
        c.setFillColor(colors.white); c.setFont(sans, 8.0); self._draw_wrapped(c, d.opportunity_metric_basis or "A quantified opportunity will be included once the relevant commercial inputs have been confirmed.", 347, 363, 190, 12, 4, sans)
        # insights
        c.setFillColor(INK); c.setFont(sans, 6.8); c.drawString(33, 253, "T H R E E   I N S I G H T S   T O   E X P L O R E")
        cols = (33, 215, 397)
        for index, (x, insight) in enumerate(zip(cols, d.insights), 1):
            c.setFillColor(COPPER); c.setFont(serif, 20); c.drawString(x, 215, f"0{index}")
            self._draw_image_or_panel(c, d.insight_images[index - 1], x + 43, 187, 112, 28, colors.HexColor("#B7A48A"), "")
            c.setFillColor(INK); c.setFont(sans, 7.5); self._draw_wrapped(c, insight.title, x, 176, 160, 10, 2, sans, bold=True)
            c.setFont(sans, 6.8); self._draw_wrapped(c, insight.body, x, 150, 157, 9.2, 7, sans)
        self._footer(c, w, sans, 1)
        self._draft_flag(c, w, h, sans, d)

    def _page_two(self, c: Canvas, w: float, h: float, serif: str, sans: str, d: FieldworkProposalDraft) -> None:
        c.setFillColor(IVORY)
        c.rect(0, 0, w, h, stroke=0, fill=1)
        c.setFillColor(INK); c.setFont(sans, 8); c.drawString(33, h - 42, _caps(d.company))
        c.setFont(sans, 5.8); c.drawString(33, h - 54, "F I E L D W O R K   P R O P O S A L")
        c.setStrokeColor(RULE); c.setLineWidth(.5); c.line(33, h - 64, w - 31, h - 64)
        c.setFillColor(INK); c.setFont(serif, 27); self._draw_wrapped(c, "From opportunity to a clearer plan.", 33, h - 92, 330, 33, 3, serif)
        c.setFont(sans, 8.3); self._draw_wrapped(c, "FIELDWORK will explore, validate and define the most valuable growth opportunities — then give you a clear, practical plan to move forward with confidence.", 33, h - 178, 330, 12, 4, sans)
        c.setStrokeColor(RULE); c.line(438, h - 92, 438, h - 224)
        c.setFillColor(INK); c.setFont(serif, 17); self._draw_wrapped(c, "A clearer choice creates momentum.", 455, h - 95, 105, 22, 3, serif)
        c.setStrokeColor(COPPER); c.setLineWidth(1.1); c.line(455, h - 188, 480, h - 188)
        c.setFillColor(INK); c.setFont(sans, 5.8); c.drawString(455, h - 207, _caps(d.company))
        c.setFont(sans, 6.6); c.drawString(33, h - 251, "W H A T   Y O U ' L L   R E C E I V E")
        xs = (33, 211, 389)
        for i, (x, item) in enumerate(zip(xs, d.deliverables), 1):
            self._draw_image_or_panel(c, d.insight_images[i - 1], x, h - 341, 160, 72, colors.HexColor("#B7A48A"), "")
            c.setFillColor(INK); c.setFont(serif, 10.8); self._draw_wrapped(c, f"{i}. {item.title}", x, h - 350, 160, 13, 2, serif)
            c.setFont(sans, 6.8); self._draw_wrapped(c, item.body, x, h - 380, 160, 9.2, 5, sans)
        self._draw_image_or_panel(c, d.banner_image or d.hero_image, 0, 188, w, 145, FOREST, "")
        c.setFillColor(colors.white); c.setFont(serif, 24); self._draw_wrapped(c, d.closing_headline, 33, 299, 300, 28, 3, serif)
        c.setStrokeColor(COPPER); c.setLineWidth(1.2); c.line(33, 233, 58, 233)
        c.setFont(sans, 8.4); self._draw_wrapped(c, d.closing_body, 33, 219, 300, 12, 2, sans)
        c.setFillColor(IVORY); c.rect(0, 0, w, 188, stroke=0, fill=1)
        c.setFillColor(INK); c.setFont(sans, 6.7); c.drawString(33, 170, "E N G A G E M E N T   D E T A I L S")
        c.setStrokeColor(RULE); c.setLineWidth(.5); c.line(33, 162, w - 31, 162)
        labels = ("TIMELINE", "INVESTMENT", "FOCUS", "NEXT STEP")
        values = (d.timeline, d.investment or "To be agreed", d.focus, "Approve FIELDWORK")
        for index, (label, value) in enumerate(zip(labels, values)):
            x = 33 + index * 137
            if index: c.setStrokeColor(RULE); c.line(x - 12, 37, x - 12, 148)
            c.setFillColor(COPPER); c.setFont(serif, 20); c.drawString(x, 122, ("◌" if index != 1 else "◇"))
            c.setFillColor(INK); c.setFont(sans, 5.6); c.drawString(x + 27, 139, _caps(label))
            c.setFont(serif, 12 if index != 1 else 15); self._draw_wrapped(c, value, x + 27, 127, 95, 14, 3, serif)
        self._footer(c, w, sans, 2)
        self._draft_flag(c, w, h, sans, d)

    @staticmethod
    def _draw_wrapped(c: Canvas, text: str, x: float, y: float, width: float, leading: float, max_lines: int, font: str, bold: bool = False) -> None:
        words, lines, line = str(text).split(), [], ""
        size = c._fontsize
        for word in words:
            candidate = (line + " " + word).strip()
            if c.stringWidth(candidate, font, size) <= width or not line:
                line = candidate
            else:
                lines.append(line); line = word
        if line: lines.append(line)
        if len(lines) > max_lines:
            lines = lines[:max_lines]; lines[-1] = lines[-1].rstrip(".,;: ") + "…"
        for item in lines:
            c.drawString(x, y, item)
            y -= leading

    @staticmethod
    def _draw_image_or_panel(c: Canvas, asset: VisualAssetRef | None, x: float, y: float, width: float, height: float, fallback, label: str) -> None:
        try:
            image = Path(asset.path if asset else "")
            if image.is_file():
                c.drawImage(ImageReader(str(image)), x, y, width=width, height=height, preserveAspectRatio=False, mask="auto")
                return
        except Exception:
            pass
        c.setFillColor(fallback); c.rect(x, y, width, height, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#D7C6AB")); c.circle(x + width * .68, y + height * .62, min(width, height) * .25, stroke=0, fill=1)

    @staticmethod
    def _footer(c: Canvas, width: float, sans: str, page: int) -> None:
        c.setStrokeColor(RULE); c.setLineWidth(.4); c.line(33, 28, width - 31, 28)
        c.setFillColor(INK); c.setFont(sans, 7); c.drawString(33, 15, "NARRATIIVE")
        c.setFont(sans, 5.2); c.drawString(33, 7, "THE GROWTH AGENCY FOR AMBITIOUS BRANDS")
        c.drawRightString(width - 31, 11, f"0{page} / 02")

    @staticmethod
    def _draft_flag(c: Canvas, width: float, height: float, sans: str, d: FieldworkProposalDraft) -> None:
        if d.internal_review_only:
            c.saveState(); c.setFillColor(colors.HexColor("#8B5A32")); c.setFont(sans, 5.6)
            c.drawRightString(width - 31, height - 31, "INTERNAL REVIEW DRAFT — NOT FOR CLIENT RELEASE")
            c.restoreState()


def _caps(value: str) -> str:
    return " ".join(str(value).upper().split())


def _valid_fee_binding(binding: Mapping[str, str] | None) -> bool:
    return bool(binding and binding.get("approval_id") and re.fullmatch(r"[0-9a-f]{64}", str(binding.get("fee_checksum") or "")))


def _validate_client_language(value: str) -> None:
    prohibited = (r"\bgrowth sprint\b", r"\bgate\s*\d+\b", r"\bhuman review\b", r"\bworkflow\b", r"\bworkflow run\b", r"\bsynthetic diagnostic\b", r"\bevidence reconciliation\b", r"\bapproval status\b", r"\brun[-_ ]?[a-z0-9]", r"\bartifact[-_]")
    if any(re.search(pattern, value, flags=re.I) for pattern in prohibited):
        raise FieldworkProposalRenderError("FIELDWORK client presentation contains internal workflow terminology")


def _validate_editorial_specificity(draft: FieldworkProposalDraft, visible: str) -> None:
    """Reject known placeholder language and repetitive insight framing."""
    placeholders = (
        "an opportunity worth validating",
        "to validate",
        "one business story",
        "a sharper audience choice",
        "growth that can be measured",
    )
    normalised = " ".join(visible.casefold().split())
    if any(phrase in normalised for phrase in placeholders):
        raise FieldworkProposalRenderError("FIELDWORK proposal contains generic placeholder copy")
    titles = [" ".join(item.title.casefold().split()) for item in draft.insights]
    if len(set(titles)) != 3 or any(len(item.body.split()) < 8 for item in draft.insights):
        raise FieldworkProposalRenderError("FIELDWORK insights must be differentiated and commercially substantive")
