"""Reusable, approval-gated production of editable Growth Blueprint deliverables.

The structured Growth Blueprint remains the strategic source of truth.  This
module only creates a presentation specification and records deterministic
rendering/visual-QA evidence; it never edits the source blueprint or releases a
client-facing artefact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Protocol

from runtime.fieldwork_v4 import (
    FIELDWORK_V4_OPENING_TITLES,
    build_fieldwork_v4_cohort_model,
    validate_fieldwork_v4_opening,
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value))


def _text(value: Any, limit: int = 480) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    prefix = text[:limit]
    sentence_ends = [match.end() for match in re.finditer(r"[.!?](?=\s|$)", prefix)]
    if sentence_ends and sentence_ends[-1] >= min(80, limit // 2):
        return prefix[:sentence_ends[-1]].rstrip()
    cut = prefix.rfind(" ")
    return text[: cut if cut > 24 else limit].rstrip(" ,;:") + "."


def _client_copy(value: Any, limit: int = 210) -> str:
    """Remove implementation identifiers from visible presentation copy."""
    text = re.sub(r"\(?\s*(?:ev_[A-Za-z0-9_-]+|artifact-[A-Za-z0-9_-]+|workflow[_-][A-Za-z0-9_-]+)(?:\s*,\s*(?:ev_|artifact-|workflow[_-])[A-Za-z0-9_-]+)*\s*\)?", "", str(value or ""))
    text = re.sub(r"\b(?:activation_implications|market_category_diagnosis|growth_barriers|source_of_difference|growth_opportunity|evidence_and_uncertainty|key_strategic_choices|fact_interpretation_hypothesis_lineage)\b", "", text, flags=re.I)
    text = " ".join(text.split()).strip(" ,;:")
    return _text(text, limit)


def _complete_client_sentence(value: Any, limit: int) -> str:
    text = _client_copy(value, limit).strip()
    if text and not text.endswith((".", "?", "!")):
        text += "."
    return text


def _safe_rendered_path(output_dir: Path, value: Any, *, suffix: str) -> Path:
    root = output_dir.resolve()
    candidate = Path(str(value or ""))
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate.parent != root or candidate.suffix.casefold() != suffix:
        raise RuntimeError("presentation renderer returned an unsafe output path")
    return candidate


@dataclass(frozen=True, slots=True)
class PresentationSlideSpec:
    slide_no: int
    title: str
    takeaway: str
    body: str
    visual_treatment: str
    evidence_refs: tuple[str, ...] = ()
    source_notes: tuple[str, ...] = ()
    layout_type: str = "evidence_implication"
    citation_labels: tuple[str, ...] = ()
    claim_status: str = ""
    content_data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_no": self.slide_no,
            "title": self.title,
            "takeaway": self.takeaway,
            "body": self.body,
            "visual_treatment": self.visual_treatment,
            "evidence_refs": list(self.evidence_refs),
            "source_notes": list(self.source_notes),
            "layout_type": self.layout_type,
            "citation_labels": list(self.citation_labels),
            "claim_status": self.claim_status,
            "content_data": dict(self.content_data),
        }


@dataclass(frozen=True, slots=True)
class PresentationSpecification:
    specification_id: str
    source_blueprint_id: str
    source_blueprint_version: int
    workspace_id: str
    client_id: str
    title: str
    status: str
    template_source: str
    slides: tuple[PresentationSlideSpec, ...]
    source_checksum: str
    strategic_source_unchanged: bool = True
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 12 <= len(self.slides) <= 40:
            raise ValueError("presentation specification must contain between 12 and 40 slides")
        numbers = tuple(slide.slide_no for slide in self.slides)
        if numbers != tuple(range(1, len(self.slides) + 1)):
            raise ValueError("presentation slides must be ordered from 1")
        if self.status != "ready_for_production":
            raise ValueError("presentation specification must be ready_for_production")

    def to_dict(self) -> dict[str, Any]:
        return {
            "specification_id": self.specification_id,
            "source_blueprint_id": self.source_blueprint_id,
            "source_blueprint_version": self.source_blueprint_version,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "title": self.title,
            "status": self.status,
            "template_source": self.template_source,
            "slides": [slide.to_dict() for slide in self.slides],
            "source_checksum": self.source_checksum,
            "strategic_source_unchanged": self.strategic_source_unchanged,
            "notes": list(self.notes),
        }


ARCHETYPE_LIBRARY = (
    "thesis", "provocation", "question", "market_forces", "comparison",
    "competitive_landscape", "sea_of_sameness", "opportunity", "audience",
    "demand_pools", "evidence_board", "journey", "entry_points", "diagnosis",
    "positioning", "positioning_map", "narrative", "message_architecture",
    "commercial_model", "flywheel", "channel_roles", "campaign_system",
    "roadmap", "prioritisation", "measurement", "closing",
)

CANONICAL_BLUEPRINT_SLIDE_TITLES = FIELDWORK_V4_OPENING_TITLES + (
    "Competitive Landscape", "The Sea of Sameness",
    "The Market Gap", "Growth Constraint Diagnosis", "The Provocation",
    "Audience Reality", "Audience Segments / Demand Pools", "Customer Evidence Board",
    "Audience Tensions / Decision Context", "Category Entry Points", "Current Brand Diagnosis",
    "Positioning Problem", "Strategic Positioning", "Positioning Map", "Narrative Platform",
    "Core Message Architecture", "Messaging Territories / Distinctive Assets",
    "Commercial Prize", "Attention Strategy", "Channel Roles", "Content / Campaign System",
    "Creative Direction / Next-Phase Hook", "Growth Priorities / 90-Day Activation Plan",
    "Measurement Framework", "Strategic Principle / Closing Mandate",
)


def build_blueprint_director_presentation_spec(
    artifact: Mapping[str, Any], *, specification_id: str, source_blueprint_id: str,
    source_blueprint_version: int, workspace_id: str, client_id: str, title: str,
    brand_name: str,
) -> PresentationSpecification:
    """Render the approved Blueprint Director story without rewriting its argument."""
    blueprint = artifact.get("client_facing_blueprint")
    trace = artifact.get("editorial_trace")
    if not isinstance(blueprint, Mapping) or not isinstance(blueprint.get("pages"), list):
        raise ValueError("Blueprint Director source is incomplete")
    trace_by_page = {
        item.get("page_number"): item
        for item in trace or []
        if isinstance(item, Mapping)
    }
    slides = []
    for page in blueprint["pages"]:
        if not isinstance(page, Mapping):
            raise ValueError("Blueprint Director pages must be objects")
        number = int(page.get("page_number") or 0)
        evidence = trace_by_page.get(number, {})
        slides.append(PresentationSlideSpec(
            slide_no=number,
            title=_client_copy(page.get("headline"), 120),
            takeaway=_client_copy(page.get("commercial_consequence"), 180),
            body=_client_copy(page.get("body"), 420),
            visual_treatment=_client_copy(page.get("visual_opportunity"), 120),
            evidence_refs=tuple(str(ref) for ref in evidence.get("evidence_refs") or [] if str(ref).strip()),
            source_notes=("Detailed evidence lineage is retained in the immutable Blueprint Director review record.",),
            layout_type=str(page.get("visual_archetype") or ("cover" if number == 1 else "evidence_implication")),
        ))
    return PresentationSpecification(
        specification_id=specification_id,
        source_blueprint_id=source_blueprint_id,
        source_blueprint_version=source_blueprint_version,
        workspace_id=workspace_id,
        client_id=client_id,
        title=title,
        status="ready_for_production",
        template_source="Narratiive Blueprint Director editorial commission using the Rave benchmark as calibre only.",
        slides=tuple(slides),
        source_checksum=_checksum(artifact),
        notes=(
            "INTERNAL REVIEW DRAFT — HUMAN APPROVAL REQUIRED",
            "Visible copy is the approved Blueprint Director output; evidence governance remains backstage.",
        ),
    )


def _human_source_note(section: str) -> str:
    return f"Internal provenance retained for {section}; detailed evidence remains in the review record."


def build_directed_growth_blueprint_presentation_spec(
    artifact: Mapping[str, Any], *, specification_id: str, source_blueprint_id: str,
    source_blueprint_version: int, workspace_id: str, client_id: str, title: str,
    brand_name: str,
) -> PresentationSpecification:
    """Create a director-led, variable-length story from the approved strategy.

    This is deliberately an editorial plan, not a field-to-slide dump.  Raw
    evidence identifiers stay in the immutable source and speaker notes, never
    in visible client copy.  A frontier Presentation Director can replace this
    rule-based director through the same normalized specification contract.
    """
    sections = {key: _section(artifact, key) for key in (
        "market_category_diagnosis", "audience", "growth_barriers", "source_of_difference",
        "positioning", "narrative", "growth_opportunity", "activation_implications",
        "key_strategic_choices", "evidence_and_uncertainty")}
    def text(key: str, field: str = "diagnosis", limit: int = 300) -> str:
        value: Any = sections[key].get(field)
        if not value and key == "key_strategic_choices":
            raw = artifact.get(key)
            if isinstance(raw, list):
                value = " ".join(str(item.get("choice") or item.get("decision") or item) for item in raw[:2])
        return _client_copy(value, min(limit, 150)) or "The approved source does not support a stronger conclusion here."
    def refs(key: str) -> tuple[str, ...]:
        return tuple(str(v) for v in sections[key].get("evidence_refs") or () if str(v).strip())
    brand = _client_copy(brand_name, 100)
    if not brand:
        raise ValueError("brand_name is required for presentation production")
    # The sequence follows an argument: case for change -> diagnosis -> choice -> activation.
    plan = [
        ("The Narratiive Growth Blueprint", brand, "Strategic clarity for scalable growth.", "thesis", "growth_opportunity"),
        ("The executive thesis", text("growth_opportunity"), "The answer is a choice about clarity, memory and momentum.", "thesis", "growth_opportunity"),
        ("The commercial question", f"Where could {brand}'s next meaningful growth come from?", "Move from marketing activity to being easier to choose.", "question", "evidence_and_uncertainty"),
        ("Market reality", text("market_category_diagnosis"), "New category conditions change what growth must earn.", "market_forces", "market_category_diagnosis"),
        ("Category growth dynamics", text("market_category_diagnosis", "implication"), "Name the battlefield: demand, distinction, distribution or trust.", "comparison", "market_category_diagnosis"),
        ("Competitive landscape", text("source_of_difference"), "The category's default behaviour is visible in how brands compete.", "competitive_landscape", "source_of_difference"),
        ("The Sea of Sameness", "The category's language and visual codes are converging.", f"When familiar category promises become interchangeable, {brand} needs a more memorable reason to be chosen.", "sea_of_sameness", "source_of_difference"),
        ("The market gap", text("growth_opportunity"), "The opportunity is a new interpretation of the category, not simply another audience.", "opportunity", "growth_opportunity"),
        ("Growth constraint diagnosis", text("growth_barriers"), "Weak growth is not automatically a channel problem.", "diagnosis", "growth_barriers"),
        ("The provocation", f"{brand} cannot scale a trust-dependent proposition while its proof remains unresolved.", "Resolve the contradiction before buying more attention.", "provocation", "growth_barriers"),
        ("Audience reality", text("audience"), "The future growth audience may not look like today's customer.", "audience", "audience"),
        ("Audience segments / demand pools", text("audience", "implication"), "Segment by growth opportunity, not persona fiction.", "demand_pools", "audience"),
        ("Customer evidence board", text("audience"), "Observed signals are directional; interpretation remains bounded.", "evidence_board", "audience"),
        ("Audience tensions / decision context", text("audience", "implication"), "Confidence is built or lost at specific moments.", "journey", "audience"),
        ("Category entry points", text("positioning"), f"The planning question is when {brand} should be remembered.", "entry_points", "positioning"),
        ("Current brand diagnosis", text("source_of_difference"), f"Earn trust by being candid about what {brand} currently means.", "comparison", "source_of_difference"),
        ("The positioning problem", text("positioning"), "The gap is between what the business says and what the market hears.", "diagnosis", "positioning"),
        ("Strategic positioning", text("positioning", "implication"), "Make the strategic anchor brutally simple and testable.", "positioning", "positioning"),
        ("Positioning map", text("positioning"), "Use axes that expose strategic tension, not generic premium/value.", "positioning_map", "positioning"),
        ("Narrative platform", text("narrative"), "Tension, shift and resolution join insight to activation.", "narrative", "narrative"),
        ("Core message architecture", text("narrative", "implication"), "Messaging is a decision system, not a slogan bank.", "message_architecture", "narrative"),
        ("Messaging territories", text("narrative"), "Each territory has a job: trust, desire, risk reduction or action.", "comparison", "narrative"),
        ("Distinctive assets", "Distinctiveness should compound as recognisable verbal, visual and tonal codes.", f"Build a small set of codes that make {brand} recognisable before the logo appears.", "evidence_board", "source_of_difference"),
        ("Attention strategy", text("activation_implications"), "The question is what people will notice, remember and connect.", "flywheel", "activation_implications"),
        ("Channel roles", text("activation_implications", "implication"), "Every channel earns one strategic role.", "channel_roles", "activation_implications"),
        ("Content / campaign system", text("narrative", "implication"), "Narrative becomes themes, campaigns, assets, distribution and learning.", "campaign_system", "narrative"),
        ("Creative territories / lookbook", text("activation_implications"), "Translate only the approved activation implications into distinctive creative routes for testing.", "creative_territories", "activation_implications"),
        ("90-day activation plan", text("key_strategic_choices", "implication"), "Prove the strategy before scaling it.", "roadmap", "key_strategic_choices"),
        ("Measurement framework", "Measurement must capture movement in attention, confidence, choice and repeat.", "Set baselines and guardrails across attention, search, conversion, repeat and learning.", "measurement", "evidence_and_uncertainty"),
        ("Strategic principle / closing mandate", f"Make {brand} easier to notice, trust, remember and choose.", "The strategy is to make the proposition easier to trust, understand and choose before scaling activity.", "closing", "key_strategic_choices"),
    ]
    slides = tuple(PresentationSlideSpec(
        slide_no=i, title=heading, takeaway=takeaway, body=body,
        visual_treatment=archetype, evidence_refs=refs(section),
        source_notes=(_human_source_note(section),), layout_type=archetype,
    ) for i, (heading, takeaway, body, archetype, section) in enumerate(plan, 1))
    return PresentationSpecification(
        specification_id=specification_id, source_blueprint_id=source_blueprint_id,
        source_blueprint_version=source_blueprint_version, workspace_id=workspace_id,
        client_id=client_id, title=title, status="ready_for_production",
        template_source="Narratiive editorial grammar: dark ink, warm ivory, amber accent, serif hero typography and variable editorial pacing.",
        slides=slides, source_checksum=_checksum(artifact),
        notes=("INTERNAL REVIEW DRAFT — HUMAN APPROVAL REQUIRED", "Presentation Director plan; raw lineage is retained in notes and source records."),
    )


def _section(artifact: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = artifact.get(key) or {}
    return value if isinstance(value, Mapping) else {}


def build_growth_blueprint_presentation_spec(
    artifact: Mapping[str, Any],
    *,
    specification_id: str,
    source_blueprint_id: str,
    source_blueprint_version: int,
    workspace_id: str,
    client_id: str,
    title: str,
    brand_name: str,
) -> PresentationSpecification:
    """Map the canonical structured output to the fixed master Blueprint story.

    The mapper only selects and shortens existing fields. It does not create or
    revise strategic conclusions, numbers, evidence or recommendations.
    """

    brand = _client_copy(brand_name, 100)
    if not brand:
        raise ValueError("brand_name is required for presentation production")
    sections = {
        key: _section(artifact, key)
        for key in (
            "market_category_diagnosis",
            "audience",
            "growth_barriers",
            "source_of_difference",
            "positioning",
            "narrative",
            "growth_opportunity",
            "activation_implications",
            "key_strategic_choices",
            "evidence_and_uncertainty",
        )
    }
    refs = lambda key: tuple(str(item) for item in sections[key].get("evidence_refs") or () if str(item).strip())
    diag = lambda key: _text(sections[key].get("diagnosis"), 300)
    implication = lambda key: _text(sections[key].get("implication"), 220)
    uncertainty = lambda key: _text((sections[key].get("uncertainties") or [""])[0], 180)

    plan = [
        ("Cover", "The strategic answer is a bounded, testable opportunity rather than a forecast.", diag("growth_opportunity"), "thesis", "statement"),
        ("Executive Thesis", f"{brand}'s next growth question is about where existing strengths can compound.", diag("growth_opportunity"), "thesis", "statement"),
        ("The Commercial Question", f"Where could {brand}'s next meaningful growth come from?", "This deck separates what outside-in evidence supports from what only company access can answer.", "question", "statement"),
        ("Market Reality", f"Category context creates pressure, but does not diagnose {brand} by itself.", diag("market_category_diagnosis"), "market", "comparison"),
        ("Category growth dynamics", "Premiumisation and category polarisation make the middle harder to defend.", uncertainty("market_category_diagnosis"), "market", "framework"),
        ("Competitive landscape", f"Competitors own different trust and value cues; {brand}'s combination remains a hypothesis.", diag("source_of_difference"), "competition", "comparison"),
        ("The sea of sameness", f"{brand} needs a reason to be remembered, not another generic category claim.", implication("source_of_difference"), "competition", "comparison"),
        ("The market gap", "The opportunity is a specific, reversible bet grounded in the evidence available.", diag("growth_opportunity"), "opportunity", "matrix"),
        ("Growth constraint diagnosis", "Trust and conversion are constrained by unresolved proof and proposition questions.", diag("growth_barriers"), "constraint", "framework"),
        ("The provocation", "A public trust contradiction can undermine a trust-dependent growth story.", implication("growth_barriers"), "constraint", "statement"),
        ("Audience reality", "Outside-in evidence cannot yet support confident buyer segmentation.", diag("audience"), "audience", "comparison"),
        ("Audience segments / demand pools", "Potential buyer jobs are a research question, not a settled segment model.", uncertainty("audience"), "audience", "framework"),
        ("Customer evidence board", "The available customer signal is directional, small and self-selected.", diag("audience"), "audience", "evidence"),
        ("Audience tensions / decision context", "The useful tension is between breadth of appeal and clarity of choice.", implication("audience"), "audience", "framework"),
        ("Category entry points", "Different entry points may require different proof and proposition jobs.", diag("positioning"), "positioning", "framework"),
        ("Current brand diagnosis", f"{brand}'s current proposition is observable; its effectiveness is not proven.", diag("source_of_difference"), "positioning", "comparison"),
        ("Positioning problem", "The positioning hypothesis depends on resolving a credibility contradiction first.", diag("positioning"), "positioning", "tension"),
        ("Strategic positioning", "The approved positioning is a testable strategic hypothesis, not a proven market fact.", diag("positioning"), "positioning", "statement"),
        ("Positioning map", f"{brand} should test ownable territory against real customer perception, not marketing copy alone.", uncertainty("positioning"), "positioning", "matrix"),
        ("Narrative platform", "A clearer progression could turn breadth of range into a guided reason to return.", diag("narrative"), "narrative", "framework"),
        ("Core message architecture", "One front door can make two subscription jobs easier to understand.", implication("narrative"), "narrative", "framework"),
        ("Messaging territories / distinctive assets", "Distinctiveness must be earned through proof, not asserted through tone.", uncertainty("narrative"), "narrative", "comparison"),
        ("Commercial Prize", "The commercial prize is better conversion and repeat behaviour, not activity for its own sake.", diag("growth_opportunity"), "commercial", "statement"),
        ("Attention strategy", "Attention should make the specific proposition easier to notice and remember.", diag("activation_implications"), "activation", "framework"),
        ("Channel roles", "Channels remain hypotheses until channel economics and conversion evidence are available.", uncertainty("activation_implications"), "activation", "comparison"),
        ("Content / campaign system", "Execution should test the proposition architecture, not multiply generic content.", implication("activation_implications"), "activation", "framework"),
        ("Creative direction / next-phase hook", "Creative development should follow the resolved strategic tension.", uncertainty("activation_implications"), "activation", "statement"),
        ("Growth priorities / 90-day activation plan", "Start with a capped, reversible test and a separate claims audit.", implication("activation_implications"), "activation", "matrix"),
        ("Measurement framework", "Success depends on agreed baselines, guardrails and falsification conditions.", implication("growth_opportunity"), "measurement", "framework"),
        ("Strategic principle / closing mandate", "Make the proposition easier to trust, understand and choose before scaling activity.", diag("key_strategic_choices") or diag("growth_opportunity"), "closing", "statement"),
    ]
    slides = tuple(
        PresentationSlideSpec(
            slide_no=index,
            title=CANONICAL_BLUEPRINT_SLIDE_TITLES[index - 1],
            takeaway=takeaway,
            body=body or "The source artefact does not provide enough evidence for a stronger claim.",
            visual_treatment=visual,
            evidence_refs=refs({1: "growth_opportunity", 2: "growth_opportunity", 3: "evidence_and_uncertainty", 4: "market_category_diagnosis", 5: "market_category_diagnosis", 6: "source_of_difference", 7: "source_of_difference", 8: "growth_opportunity", 9: "growth_barriers", 10: "growth_barriers", 11: "audience", 12: "audience", 13: "audience", 14: "audience", 15: "positioning", 16: "source_of_difference", 17: "positioning", 18: "positioning", 19: "positioning", 20: "narrative", 21: "narrative", 22: "narrative", 23: "growth_opportunity", 24: "activation_implications", 25: "activation_implications", 26: "activation_implications", 27: "activation_implications", 28: "activation_implications", 29: "growth_opportunity", 30: "key_strategic_choices"}[index]),
            source_notes=("Source: immutable structured Growth Blueprint artefact; presentation formatting does not change the strategic source.",),
            layout_type="cover" if index == 1 else ("statement" if visual == "statement" else "evidence_implication"),
        )
        for index, (title_text, takeaway, body, visual, _section_name) in enumerate(plan, start=1)
    )
    if tuple(slide.title for slide in slides) != CANONICAL_BLUEPRINT_SLIDE_TITLES:
        raise ValueError("canonical Blueprint presentation plan no longer matches Schema v3")
    source_checksum = _checksum(artifact)
    return PresentationSpecification(
        specification_id=specification_id,
        source_blueprint_id=source_blueprint_id,
        source_blueprint_version=source_blueprint_version,
        workspace_id=workspace_id,
        client_id=client_id,
        title=title,
        status="ready_for_production",
        template_source="Narratiive Blueprint canon v1 visual framework library and visual intelligence system; native PPTX template not present in repository",
        slides=slides,
        source_checksum=source_checksum,
        notes=("INTERNAL REVIEW DRAFT — HUMAN APPROVAL REQUIRED",),
    )


@dataclass(frozen=True, slots=True)
class VisualQAResult:
    status: str
    checks: Mapping[str, bool]
    findings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "passed" and all(self.checks.values())

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "checks": dict(self.checks), "findings": list(self.findings)}


def presentation_quality_checks(specification: PresentationSpecification) -> dict[str, bool]:
    """Deterministic editorial checks applied before human visual review."""
    visible = " ".join(f"{s.title} {s.takeaway} {s.body}" for s in specification.slides).lower()
    seven_chapter_demo = "seven-chapter issue #471 demonstration profile" in specification.template_source.casefold()
    founder_quality_profile = "issue #473 founder-quality controls" in specification.template_source.casefold()
    by_number = {slide.slide_no: slide for slide in specification.slides}
    slide_8 = by_number.get(8, PresentationSlideSpec(8, "", "", "", "")).content_data
    slide_13 = by_number.get(13, PresentationSlideSpec(13, "", "", "", "")).content_data
    slide_22 = by_number.get(22, PresentationSlideSpec(22, "", "", "", "")).content_data
    substantive_roles = (
        all(bool(slide_8.get(key)) for key in ("x_axis", "y_axis", "competitors", "current_position", "future_position", "market_gap", "audience", "competitor_miss"))
        and len(slide_13.get("signals") or []) >= 3
        and len(slide_13.get("customer_language") or []) >= 2
        and bool(slide_13.get("language_status"))
        and all(key in by_number.get(19, PresentationSlideSpec(19, "", "", "", "")).content_data for key in ("x_axis", "y_axis", "positions", "territory"))
        and len(slide_22.get("territories") or []) >= 3
        and all(len(slide_22.get(key) or []) >= 2 for key in ("verbal_assets", "tone_motion_cues", "recurring_formats"))
    )
    common = {
        "editorial_arc_is_complete": (
            bool(specification.slides)
            and [slide.slide_no for slide in specification.slides]
            == list(range(1, len(specification.slides) + 1))
        ),
        "visual_forms_are_intentional": all(
            bool(slide.layout_type.strip()) and bool(slide.visual_treatment.strip())
            for slide in specification.slides
        ),
        "no_visible_machine_runtime_artefacts": not any(token.lower() in visible for token in ("ev_", "artifact-", "workflow_run", "evidence / source refs")),
        "conclusion_led_headlines": sum(bool(s.takeaway.strip()) for s in specification.slides) >= len(specification.slides) * 0.9,
        "source_provenance_retained": all(s.source_notes for s in specification.slides),
        "readable_citations_present": all(
            slide.slide_no == 1 or bool(slide.citation_labels)
            for slide in specification.slides
        ),
        "claim_status_is_visible": all(
            slide.slide_no == 1 or bool(slide.claim_status.strip())
            for slide in specification.slides
        ),
        "quantified_commercial_model_present": any(
            slide.layout_type == "commercial_model" and bool(slide.content_data.get("scenarios"))
            for slide in specification.slides
        ),
        "source_register_present": any(
            bool(slide.content_data.get("source_register_entries"))
            for slide in specification.slides
        ),
        "strategic_source_unchanged": specification.strategic_source_unchanged,
    }
    if seven_chapter_demo:
        required_chapters = {
            "The Opportunity", "The Constraint", "The Advantage", "The Strategy",
            "The Creative Future", "The Growth Engine", "The Next 12 Months",
        }
        titles = {slide.title for slide in specification.slides}
        demonstration_checks = {
            **common,
            "seven_chapter_demonstration_profile_is_complete": (
                len(specification.slides) >= 12 and required_chapters.issubset(titles)
            ),
            "mandatory_opening_five_are_distinct": len({slide.title for slide in specification.slides[:5]}) == 5,
            "locked_canon_is_declared_unchanged": "locked production canon unchanged" in specification.template_source.casefold(),
        }
        if founder_quality_profile:
            commercial_slides = [
                slide for slide in specification.slides
                if slide.layout_type == "commercial_model"
            ]
            demonstration_checks.update(
                {
                    "founder_quality_commercial_case_includes_investment": (
                        len(commercial_slides) == 1
                        and bool(commercial_slides[0].content_data.get("investment_case"))
                        and all(
                            "year_one_net_after_investment" in scenario
                            for scenario in commercial_slides[0].content_data.get("scenarios") or []
                        )
                    ),
                    "founder_quality_creative_proof_is_present": any(
                        slide.layout_type == "creative_proof"
                        and bool(slide.content_data.get("asset_path"))
                        for slide in specification.slides
                    ),
                    "founder_quality_close_asks_for_a_decision": (
                        specification.slides[-1].title == "The founder decision"
                    ),
                }
            )
        return demonstration_checks
    return {
        **common,
        "canonical_schema_v3_slide_roles_are_preserved": (
            len(specification.slides) == 30
            and tuple(slide.title for slide in specification.slides)
            == CANONICAL_BLUEPRINT_SLIDE_TITLES
        ),
        "canonical_schema_v3_slide_roles_are_substantive": substantive_roles,
    }


def build_quantified_commercial_model(intelligence: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate a bounded opportunity model from sourced inputs and named assumptions."""
    if intelligence.get("model_type") == "new_customer_cohort":
        return build_fieldwork_v4_cohort_model(intelligence)
    raw_inputs = intelligence.get("inputs")
    raw_scenarios = intelligence.get("scenario_assumptions")
    if not isinstance(raw_inputs, list) or not isinstance(raw_scenarios, list):
        raise ValueError("commercial intelligence requires inputs and scenario assumptions")
    inputs = {
        str(item.get("input_id") or ""): item
        for item in raw_inputs
        if isinstance(item, Mapping)
    }
    try:
        market_size = Decimal(str(inputs["market_size"]["value"]))
        current_share = Decimal(str(inputs["current_market_share_percent"]["value"]))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("commercial intelligence requires numeric market size and current share") from exc
    for required in (inputs.get("market_size"), inputs.get("current_market_share_percent")):
        if not isinstance(required, Mapping) or not required.get("source_ids") or not required.get("status"):
            raise ValueError("commercial model inputs must retain source ids and evidence status")
    if market_size <= 0 or current_share < 0:
        raise ValueError("commercial model inputs must be positive")

    scenarios: list[dict[str, Any]] = []
    previous_target = current_share
    for raw in raw_scenarios:
        if not isinstance(raw, Mapping):
            raise ValueError("commercial scenario assumptions must be objects")
        try:
            target = Decimal(str(raw["target_market_share_percent"]))
            margin = Decimal(str(raw["contribution_margin_percent"]))
        except (KeyError, InvalidOperation) as exc:
            raise ValueError("commercial scenarios require target share and contribution margin assumptions") from exc
        if target <= previous_target or margin <= 0 or margin >= 100:
            raise ValueError("commercial scenarios must have increasing share and bounded margin assumptions")
        incremental_revenue = market_size * (target - current_share) / Decimal("100")
        contribution = incremental_revenue * margin / Decimal("100")
        scenarios.append({
            "name": str(raw.get("name") or "").strip(),
            "target_market_share_percent": float(target),
            "incremental_market_share_points": float(target - current_share),
            "incremental_annual_revenue": int(incremental_revenue.quantize(Decimal("1"))),
            "contribution_margin_percent_assumption": float(margin),
            "incremental_annual_contribution": int(contribution.quantize(Decimal("1"))),
            "classification": "illustrative_scenario",
        })
        previous_target = target
    if len(scenarios) != 3 or any(not item["name"] for item in scenarios):
        raise ValueError("commercial model requires named conservative, base and ambitious scenarios")

    implementation = intelligence.get("implementation_cost")
    if not isinstance(implementation, Mapping):
        raise ValueError("commercial intelligence must state implementation cost evidence")
    status = str(implementation.get("status") or "").strip()
    if status not in {"sourced", "unavailable"}:
        raise ValueError("implementation cost status must be sourced or unavailable")
    if status == "sourced" and implementation.get("value") is None:
        raise ValueError("sourced implementation cost requires a value")
    if status == "unavailable" and implementation.get("value") is not None:
        raise ValueError("unavailable implementation cost cannot contain an invented value")

    return {
        "model_id": str(intelligence.get("model_id") or "commercial-opportunity-model"),
        "currency": str(intelligence.get("currency") or "GBP"),
        "period": str(intelligence.get("period") or "annual run-rate"),
        "classification": "illustrative_scenario_model",
        "inputs": raw_inputs,
        "estimated_current_annual_revenue": int(
            (market_size * current_share / Decimal("100")).quantize(Decimal("1"))
        ),
        "scenarios": scenarios,
        "implementation_cost": dict(implementation),
        "net_value_status": "calculated" if status == "sourced" else "unavailable_pending_cost_evidence",
        "warnings": [str(item) for item in intelligence.get("warnings") or []],
    }


def commercial_model_quality_checks(model: Mapping[str, Any]) -> dict[str, bool]:
    scenarios = model.get("scenarios")
    inputs = model.get("inputs")
    implementation = model.get("implementation_cost")
    if model.get("model_type") == "new_customer_cohort":
        baseline = model.get("baseline")
        return {
            "one_to_three_scenarios_present": isinstance(scenarios, list) and 1 <= len(scenarios) <= 3,
            "cohort_population_and_period_are_explicit": bool(model.get("population")) and bool(model.get("period")),
            "qualified_visits_conversion_and_revenue_are_present": isinstance(baseline, Mapping) and all(
                key in baseline for key in (
                    "qualified_visits", "first_purchase_conversion_rate",
                    "realized_revenue_per_acquired_customer", "new_customer_cohort_revenue",
                )
            ),
            "revenue_is_not_mislabeled_as_profit": model.get("output_metric") in {"revenue", "revenue_index"},
            "existing_customer_revenue_is_separate": isinstance(model.get("existing_customer_revenue"), Mapping),
            "scenario_classification_and_assumptions_are_explicit": isinstance(scenarios, list) and all(
                isinstance(item, Mapping)
                and item.get("classification") in {"planning_case", "sensitivity", "illustrative_scenario"}
                and (item.get("classification") != "illustrative_scenario" or bool(item.get("assumptions")))
                for item in scenarios
            ),
        }
    return {
        "three_scenarios_present": isinstance(scenarios, list) and len(scenarios) == 3,
        "scenario_values_are_explicitly_illustrative": isinstance(scenarios, list) and all(
            isinstance(item, Mapping) and item.get("classification") == "illustrative_scenario"
            for item in scenarios
        ),
        "revenue_and_contribution_are_calculated": isinstance(scenarios, list) and all(
            isinstance(item, Mapping)
            and isinstance(item.get("incremental_annual_revenue"), int)
            and isinstance(item.get("incremental_annual_contribution"), int)
            for item in scenarios
        ),
        "inputs_retain_sources_and_status": isinstance(inputs, list) and all(
            isinstance(item, Mapping) and bool(item.get("source_ids")) and bool(item.get("status"))
            for item in inputs
        ),
        "implementation_cost_is_sourced_or_explicitly_unavailable": isinstance(implementation, Mapping)
        and implementation.get("status") in {"sourced", "unavailable"}
        and not (implementation.get("status") == "unavailable" and implementation.get("value") is not None),
    }


def _source_labels_for_slide(slide: PresentationSlideSpec, entries: list[Mapping[str, Any]]) -> tuple[str, ...]:
    by_page = [
        str(entry.get("source_id"))
        for entry in entries
        if slide.slide_no in (entry.get("applies_to_pages") or [])
    ]
    if by_page:
        return tuple(dict.fromkeys(by_page))
    refs = set(slide.evidence_refs)
    matched = [
        str(entry.get("source_id"))
        for entry in entries
        if refs.intersection(str(ref) for ref in entry.get("evidence_refs") or [])
    ]
    return tuple(dict.fromkeys(matched))


def _claim_status(labels: tuple[str, ...], entries: list[Mapping[str, Any]]) -> str:
    classifications = {
        str(entry.get("classification") or "").replace("_", " ").upper()
        for entry in entries
        if str(entry.get("source_id")) in labels
    }
    return " + ".join(sorted(item for item in classifications if item)) or "APPROVED STRATEGY"


def augment_specification_with_commercial_evidence(
    specification: PresentationSpecification,
    *,
    commercial_model: Mapping[str, Any],
    source_register: Mapping[str, Any],
    production_direction: Mapping[str, Any],
) -> PresentationSpecification:
    """Enrich the 30-slide FIELDWORK v4 story without rewriting its argument."""
    raw_entries = source_register.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("source register must contain readable source entries")
    entries = [entry for entry in raw_entries if isinstance(entry, Mapping)]
    source_ids = {str(entry.get("source_id") or "") for entry in entries}
    if "T1" not in source_ids or any(
        not all(str(entry.get(field) or "").strip() for field in ("source_id", "title", "publisher", "location", "classification"))
        for entry in entries
    ):
        raise ValueError("source register entries are incomplete")

    brand_name = str(production_direction.get("brand_name") or "the client").strip()
    layout_content = production_direction.get("layout_content")
    creative = production_direction.get("creative_direction")
    directed_overrides = production_direction.get("slide_overrides") or {}
    if not isinstance(layout_content, Mapping) or not isinstance(creative, Mapping):
        raise ValueError("production direction requires layout content and creative direction")
    if not isinstance(directed_overrides, Mapping):
        raise ValueError("production direction slide overrides must be a mapping")
    opening = validate_fieldwork_v4_opening(production_direction.get("fieldwork_opening") or {})

    scenarios = commercial_model.get("scenarios") or []
    model_sources = tuple(dict.fromkeys(
        str(source_id)
        for item in commercial_model.get("inputs") or []
        if isinstance(item, Mapping)
        for source_id in item.get("source_ids") or []
    ))
    if len(entries) < 3:
        raise ValueError("source register requires at least three independently identified sources")

    layout_by_slide = {
        1: "single_thesis_page", 2: "single_thesis_page", 3: "question_frame",
        4: "single_thesis_page", 5: "evidence_ladder", 6: "tension_plus_journey_matrix",
        7: "sameness_audit", 8: "market_gap_map", 9: "single_thesis_page",
        10: "provocation_page", 11: "audience_reality_split", 12: "demand_pool_cards",
        13: "customer_evidence_board", 14: "tension_plus_journey_matrix", 15: "single_thesis_page",
        16: "brand_diagnosis_scorecard", 17: "single_thesis_page", 18: "we_are_we_are_not_framework",
        19: "positioning_map", 20: "narrative_platform_framework", 21: "message_architecture",
        22: "messaging_territories", 23: "commercial_model", 24: "attention_strategy", 25: "channel_role_map",
        26: "channel_applications", 27: "creative_direction", 28: "constraint_priority_roadmap",
        29: "priority_matrix_plus_measurement_stack", 30: "closing_mandate",
    }
    content_key_by_slide = {
        1: "single_thesis_page", 2: "single_thesis_page", 3: "question_frame",
        4: "ecosystem_map_of_forces", 7: "sameness_audit", 8: "market_gap_map", 9: "brand_diagnosis_scorecard",
        10: "provocation_page", 11: "audience_reality_split", 12: "demand_pool_cards",
        13: "customer_evidence_board", 14: "tension_plus_journey_matrix", 16: "brand_diagnosis_scorecard",
        17: "we_are_we_are_not_framework", 19: "positioning_map", 20: "narrative_platform_framework",
        21: "message_architecture", 22: "messaging_territories", 23: "commercial_opportunity_model",
        24: "attention_strategy", 25: "channel_role_map",
        28: "constraint_priority_roadmap", 29: "priority_matrix_plus_measurement_stack",
        30: "closing_mandate",
    }
    base_scenario = next(
        (item for item in scenarios if str(item.get("name")).casefold() == "base"),
        scenarios[1] if len(scenarios) > 1 else scenarios[0] if scenarios else {},
    )
    scenario_revenue = int(
        base_scenario.get("new_customer_cohort_revenue")
        or base_scenario.get("incremental_annual_revenue")
        or 0
    )
    scenario_label = (
        f"index {scenario_revenue:,}"
        if commercial_model.get("currency") == "INDEX"
        else f"£{scenario_revenue / 1_000_000:.2f}m"
    )
    def opening_sources(item: Mapping[str, Any]) -> tuple[str, ...]:
        refs = set(str(ref) for ref in item.get("evidence_refs") or ())
        matched = tuple(
            str(entry.get("source_id"))
            for entry in entries
            if refs.intersection(str(ref) for ref in entry.get("evidence_refs") or ())
        )
        return tuple(dict.fromkeys(matched)) or ("T1",)

    overrides = {
        index: {
            "takeaway": item["headline"],
            "body": item["body"],
            "claim_status": item["classification"].replace("_", " ").upper(),
            "citations": opening_sources(item),
            "content": {
                **item["content"],
                "fieldwork_role": item["role"],
                "assumptions": list(item["assumptions"]),
                "visual_treatment": item["visual_treatment"],
                **({"commercial_model": dict(commercial_model)} if index == 2 else {}),
            },
        }
        for index, item in enumerate(opening, 1)
    }
    overrides.update({
        23: {
            "takeaway": f"The selected scenario models {scenario_label} for the defined new-customer cohort.",
            "body": "The cohort model separates qualified visits, first-purchase conversion and realised customer revenue. It does not claim total company revenue or profit.",
            "claim_status": "MODELLED REVENUE + ASSUMPTIONS",
            "citations": model_sources or ("T1",),
            "content": dict(commercial_model),
        },
        27: {
            "takeaway": str(creative.get("takeaway") or "The strategy translates into a distinctive, testable visual territory."),
            "body": str(creative.get("body") or "Creative direction remains a hypothesis until founder testing."),
            "claim_status": "PROPOSED CREATIVE TERRITORY",
            "citations": ("T1",), "content": dict(creative),
        },
        29: {
            "takeaway": f"Net value and payback remain unavailable until {brand_name} supplies actual margin, retention and implementation cost.",
            "body": "Track recognition, shelf comprehension and earned search share before scaling; connect them to sell-through, CAC and retention once baselines exist.",
            "claim_status": "PROPOSED MEASUREMENT + EVIDENCE GAP", "citations": ("T1",),
        },
    })
    overrides.update({int(key): dict(value) for key, value in directed_overrides.items() if isinstance(value, Mapping)})
    enriched = []
    for slide in specification.slides:
        labels = _source_labels_for_slide(slide, entries) or (("T1",) if slide.slide_no != 1 else ())
        override = overrides.get(slide.slide_no, {})
        labels = tuple(override.get("citations") or labels)
        content = dict(layout_content.get(content_key_by_slide.get(slide.slide_no, "")) or {})
        content.update(dict(override.get("content") or {}))
        if slide.slide_no == 30:
            content["source_register_entries"] = [dict(entry) for entry in entries]
            content["source_register_summary"] = "SOURCE REGISTER / governed companion deliverable included"
        enriched.append(replace(
            slide,
            takeaway=_complete_client_sentence(override.get("takeaway") or slide.takeaway, 240),
            body=_complete_client_sentence(override.get("body") or slide.body, 420),
            layout_type=layout_by_slide[slide.slide_no],
            citation_labels=labels,
            claim_status=str(override.get("claim_status") or _claim_status(labels, entries)),
            source_notes=tuple(
                f"{entry['source_id']}: {entry['publisher']} — {entry['title']} ({entry.get('date') or 'date recorded in source'}), {entry['location']}"
                for entry in entries if str(entry.get("source_id")) in labels
            ) or slide.source_notes,
            content_data=content,
        ))
    if tuple(slide.title for slide in enriched[:5]) != FIELDWORK_V4_OPENING_TITLES:
        raise ValueError("FIELDWORK v4 must preserve its five opening moves")
    return replace(
        specification,
        slides=tuple(enriched),
        notes=specification.notes + (
            "Commercial scenarios are illustrative calculations from sourced inputs and explicit assumptions.",
            "Readable slide citations resolve to the governed companion source register; detailed lineage remains in speaker notes.",
        ),
    )


def bind_source_register_to_specification(
    specification: PresentationSpecification,
    source_register: Mapping[str, Any],
) -> tuple[PresentationSpecification, dict[str, Any]]:
    """Make every visible citation and register page mapping agree exactly."""
    raw_entries = source_register.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("source register must contain readable source entries")
    pages_by_source: dict[str, list[int]] = {}
    for slide in specification.slides:
        for source_id in slide.citation_labels:
            pages_by_source.setdefault(str(source_id), []).append(slide.slide_no)
    known_ids = {str(entry.get("source_id") or "") for entry in raw_entries if isinstance(entry, Mapping)}
    unknown = sorted(set(pages_by_source) - known_ids)
    if unknown:
        raise ValueError(f"presentation cites sources missing from the source register: {unknown}")
    bound_entries = [
        {**dict(entry), "applies_to_pages": sorted(set(pages_by_source.get(str(entry.get("source_id") or ""), [])))}
        for entry in raw_entries
        if isinstance(entry, Mapping)
    ]
    bound_register = {**dict(source_register), "entries": bound_entries}
    bound_slides = []
    for slide in specification.slides:
        content = dict(slide.content_data)
        if slide.slide_no == 30:
            content["source_register_entries"] = [dict(entry) for entry in bound_entries]
        bound_slides.append(replace(slide, content_data=content))
    return replace(specification, slides=tuple(bound_slides)), bound_register


@dataclass(frozen=True, slots=True)
class DeliverableProductionRecord:
    deliverable_id: str
    workspace_id: str
    client_id: str
    source_blueprint_id: str
    source_blueprint_version: int
    specification_checksum: str
    pptx_path: str
    pdf_path: str
    status: str
    approval_status: str
    external_action_taken: bool
    visual_qa: VisualQAResult
    created_at: str
    template_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_id": self.deliverable_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "source_blueprint_id": self.source_blueprint_id,
            "source_blueprint_version": self.source_blueprint_version,
            "specification_checksum": self.specification_checksum,
            "pptx_path": self.pptx_path,
            "pdf_path": self.pdf_path,
            "status": self.status,
            "approval_status": self.approval_status,
            "external_action_taken": self.external_action_taken,
            "visual_qa": self.visual_qa.to_dict(),
            "created_at": self.created_at,
            "template_source": self.template_source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeliverableProductionRecord":
        visual_qa = value.get("visual_qa")
        if not isinstance(visual_qa, Mapping) or not isinstance(visual_qa.get("checks"), Mapping):
            raise ValueError("deliverable record contains invalid visual QA evidence")
        return cls(
            deliverable_id=str(value.get("deliverable_id") or ""),
            workspace_id=str(value.get("workspace_id") or ""),
            client_id=str(value.get("client_id") or ""),
            source_blueprint_id=str(value.get("source_blueprint_id") or ""),
            source_blueprint_version=int(value.get("source_blueprint_version")),
            specification_checksum=str(value.get("specification_checksum") or ""),
            pptx_path=str(value.get("pptx_path") or ""),
            pdf_path=str(value.get("pdf_path") or ""),
            status=str(value.get("status") or ""),
            approval_status=str(value.get("approval_status") or ""),
            external_action_taken=value.get("external_action_taken") is True,
            visual_qa=VisualQAResult(
                status=str(visual_qa.get("status") or ""),
                checks={str(key): item is True for key, item in visual_qa["checks"].items()},
                findings=tuple(str(item) for item in visual_qa.get("findings", [])),
            ),
            created_at=str(value.get("created_at") or ""),
            template_source=str(value.get("template_source") or ""),
        )


class PresentationRenderer(Protocol):
    def render(self, specification: PresentationSpecification, output_dir: Path) -> tuple[Path, Path, VisualQAResult]: ...


class FileDeliverableStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, record: DeliverableProductionRecord) -> Path:
        if not all(
            _safe_identifier(item)
            for item in (record.workspace_id, record.client_id, record.deliverable_id)
        ):
            raise ValueError("deliverable record identity must use safe identifiers")
        directory = self.root / record.workspace_id / record.client_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{record.deliverable_id}.json"
        if target.exists():
            raise ValueError("deliverable records are immutable")
        fd, temporary = tempfile.mkstemp(prefix=".deliverable-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record.to_dict(), handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target

    def load(self, workspace_id: str, client_id: str, deliverable_id: str) -> DeliverableProductionRecord | None:
        if not all(_safe_identifier(item) for item in (workspace_id, client_id, deliverable_id)):
            raise ValueError("deliverable record identity must use safe identifiers")
        target = self.root / workspace_id / client_id / f"{deliverable_id}.json"
        if not target.exists():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("deliverable record is unreadable") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("deliverable record must be an object")
        record = DeliverableProductionRecord.from_dict(payload)
        if (record.workspace_id, record.client_id, record.deliverable_id) != (
            workspace_id,
            client_id,
            deliverable_id,
        ):
            raise ValueError("deliverable record identity does not match its storage scope")
        return record


class DeliverableProductionService:
    def __init__(self, renderer: PresentationRenderer, store: FileDeliverableStore) -> None:
        self.renderer = renderer
        self.store = store

    def produce(
        self,
        artifact: Mapping[str, Any],
        *,
        specification: PresentationSpecification,
        deliverable_id: str,
        output_dir: Path,
        created_at: str,
    ) -> DeliverableProductionRecord:
        if not specification.strategic_source_unchanged:
            raise ValueError("presentation production cannot proceed with a changed strategic source")
        if specification.source_checksum != _checksum(artifact):
            raise ValueError("presentation specification source checksum does not match blueprint")
        pptx_path, pdf_path, qa = self.renderer.render(specification, Path(output_dir))
        record = DeliverableProductionRecord(
            deliverable_id=deliverable_id,
            workspace_id=specification.workspace_id,
            client_id=specification.client_id,
            source_blueprint_id=specification.source_blueprint_id,
            source_blueprint_version=specification.source_blueprint_version,
            specification_checksum=_checksum(specification.to_dict()),
            pptx_path=str(pptx_path),
            pdf_path=str(pdf_path),
            status="awaiting_review" if qa.passed else "blocked",
            approval_status="pending",
            external_action_taken=False,
            visual_qa=qa,
            created_at=created_at,
            template_source=specification.template_source,
        )
        self.store.save(record)
        return record


class FakePresentationRenderer:
    def render(self, specification: PresentationSpecification, output_dir: Path) -> tuple[Path, Path, VisualQAResult]:
        output_dir.mkdir(parents=True, exist_ok=True)
        pptx = output_dir / "blueprint.pptx"
        pdf = output_dir / "blueprint.pdf"
        pptx.write_bytes(b"PK\x03\x04 synthetic pptx")
        pdf.write_bytes(b"%PDF-1.7 synthetic pdf")
        checks = {
            "pptx_exists": True,
            "pdf_exists": True,
            "slide_sequence_complete": (
                bool(specification.slides)
                and [slide.slide_no for slide in specification.slides]
                == list(range(1, len(specification.slides) + 1))
            ),
            "source_labels_present": True,
            "no_overflow_or_overlap": True,
        }
        return pptx, pdf, VisualQAResult("passed", checks)


class LocalArtifactToolPresentationRenderer:
    """Run the repository's deterministic Artifact Tool renderer and PDF bridge."""

    def __init__(self, *, node: Path, node_modules: Path, skill_dir: Path, render_script: Path, pdf_script: Path, python: Path) -> None:
        self.node = Path(node)
        self.node_modules = Path(node_modules)
        self.skill_dir = Path(skill_dir)
        self.render_script = Path(render_script)
        self.pdf_script = Path(pdf_script)
        self.python = Path(python)

    def render(self, specification: PresentationSpecification, output_dir: Path) -> tuple[Path, Path, VisualQAResult]:
        output_dir.mkdir(parents=True, exist_ok=True)
        spec_path = output_dir / "presentation-specification.json"
        spec_path.write_text(json.dumps(specification.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        environment = dict(os.environ)
        environment.update({"RUNTIME_NODE_MODULES": str(self.node_modules), "SKILL_DIR": str(self.skill_dir), "RUNTIME_PYTHON": str(self.python)})
        subprocess.run([str(self.node), str(self.render_script), str(spec_path), str(output_dir)], check=True, env=environment, capture_output=True, text=True)
        receipt_path = output_dir / "render-receipt.json"
        if not receipt_path.is_file():
            raise RuntimeError("presentation renderer did not return a render receipt")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        pptx = _safe_rendered_path(output_dir, receipt.get("pptx"), suffix=".pptx")
        pdf = _safe_rendered_path(output_dir, receipt.get("pdf"), suffix=".pdf")
        subprocess.run([str(self.python), str(self.pdf_script), str(output_dir / ".rendered-slides"), str(pdf)], check=True, capture_output=True, text=True)
        review_script = self.render_script.parent / "review_rendered_blueprint.py"
        ocr_script = self.render_script.parent / "ocr_rendered_slides.swift"
        rendered_review_path = output_dir / "rendered-review.json"
        if not review_script.is_file() or not ocr_script.is_file():
            raise RuntimeError("rendered-slide review scripts are unavailable")
        subprocess.run(
            [
                str(self.python), str(review_script), str(output_dir / ".rendered-slides"),
                str(spec_path), str(rendered_review_path), "--ocr-script", str(ocr_script),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        validation = output_dir.parent / f"{output_dir.name}.validation.json"
        checks = {
            "pptx_exists": pptx.is_file() and pptx.stat().st_size > 0,
            "pdf_exists": pdf.is_file() and pdf.stat().st_size > 0,
            "slide_count": len(tuple((output_dir / ".rendered-slides").glob("slide-*.png"))) == len(specification.slides),
            "source_labels_present": all(slide.source_notes for slide in specification.slides),
            **presentation_quality_checks(specification),
        }
        if validation.is_file():
            payload = json.loads(validation.read_text(encoding="utf-8"))
            checks["package_integrity"] = payload.get("packageIntegrity", {}).get("status") == "pass"
            layout = payload.get("presentationLayout", {})
            checks["layout_validation"] = layout.get("finding_count") == 0 and layout.get("warning_count", 0) == 0
            checks["no_overflow_or_overlap"] = checks["layout_validation"]
        else:
            checks["no_overflow_or_overlap"] = False
        rendered_review: Mapping[str, Any] = {}
        if rendered_review_path.is_file():
            payload = json.loads(rendered_review_path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                rendered_review = payload
        rendered_checks = rendered_review.get("checks") if isinstance(rendered_review, Mapping) else None
        checks["rendered_slide_review_passed"] = (
            rendered_review.get("status") == "passed"
            and isinstance(rendered_checks, Mapping)
            and bool(rendered_checks)
            and all(item is True for item in rendered_checks.values())
        )
        findings = tuple(str(item) for item in rendered_review.get("findings") or [])
        return pptx, pdf, VisualQAResult(
            "passed" if all(checks.values()) else "failed", checks, findings
        )
