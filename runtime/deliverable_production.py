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
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, limit: int = 480) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _client_copy(value: Any, limit: int = 210) -> str:
    """Remove implementation identifiers from visible presentation copy."""
    import re
    text = re.sub(r"\(?\s*(?:ev_[A-Za-z0-9_-]+|artifact-[A-Za-z0-9_-]+|workflow[_-][A-Za-z0-9_-]+)(?:\s*,\s*(?:ev_|artifact-|workflow[_-])[A-Za-z0-9_-]+)*\s*\)?", "", str(value or ""))
    text = " ".join(text.split()).strip(" ,;:")
    return _text(text, limit)


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


def _human_source_note(section: str) -> str:
    return f"Internal provenance retained for {section}; detailed evidence remains in the review record."


def build_directed_growth_blueprint_presentation_spec(
    artifact: Mapping[str, Any], *, specification_id: str, source_blueprint_id: str,
    source_blueprint_version: int, workspace_id: str, client_id: str, title: str,
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
    # The sequence follows an argument: case for change -> diagnosis -> choice -> activation.
    plan = [
        ("The Narratiive Growth Blueprint", "Rave Coffee", "Strategic clarity for scalable growth.", "thesis", "growth_opportunity"),
        ("The thesis", text("growth_opportunity"), "The strategic answer is a bounded, testable opportunity.", "thesis", "growth_opportunity"),
        ("The commercial question", "Where could Rave's next meaningful growth come from?", "A question to resolve, not a claim to pretend is settled.", "question", "evidence_and_uncertainty"),
        ("Four forces reshape the fight", text("market_category_diagnosis"), "Market context creates pressure; it does not diagnose the business alone.", "market_forces", "market_category_diagnosis"),
        ("The category is becoming harder to remember", text("source_of_difference"), "Distinctiveness is the strategic variable to test.", "competitive_landscape", "source_of_difference"),
        ("The growth constraint", text("growth_barriers"), "Growth is constrained by unresolved proof, proposition and repeat-behaviour questions.", "diagnosis", "growth_barriers"),
        ("A useful provocation", text("growth_barriers", "implication"), "A sharper question can unlock a better decision than more activity.", "provocation", "growth_barriers"),
        ("The audience we need to understand", text("audience"), "Outside-in evidence is directional; buyer reality still needs Discovery.", "audience", "audience"),
        ("Where demand may pool", text("audience", "implication"), "Potential demand jobs are hypotheses, not settled segments.", "demand_pools", "audience"),
        ("The opportunity", text("growth_opportunity"), "A specific, reversible bet grounded in the evidence available.", "opportunity", "growth_opportunity"),
        ("The positioning choice", text("positioning"), "A position earns attention by making a choice about who it is for and against.", "positioning", "positioning"),
        ("The territory to test", text("positioning", "implication"), "The position remains a testable hypothesis until company and customer evidence validate it.", "positioning_map", "positioning"),
        ("The narrative platform", text("narrative"), "A coherent story turns a proposition into something easier to remember.", "narrative", "narrative"),
        ("From story to system", text("narrative", "implication"), "Messages and channels should each do one job in the growth system.", "message_architecture", "narrative"),
        ("The commercial mechanism", text("growth_opportunity", "implication"), "The prize is improved conversion and repeat behaviour, not activity volume.", "commercial_model", "growth_opportunity"),
        ("Activation roles", text("activation_implications"), "Execution should test the proposition architecture, not multiply generic content.", "channel_roles", "activation_implications"),
        ("What to do first", text("key_strategic_choices", "implication"), "Sequence reversible learning before irreversible scale.", "prioritisation", "key_strategic_choices"),
        ("How we will know", text("evidence_and_uncertainty", "implication"), "Agree baselines, guardrails and falsification conditions before scaling.", "measurement", "evidence_and_uncertainty"),
        ("The strategic principle", text("key_strategic_choices") or text("growth_opportunity"), "The next phase should make the proposition easier to trust, understand and choose.", "closing", "key_strategic_choices"),
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
        template_source="Narratiive editorial benchmark grammar: dark ink, warm ivory, amber accent, serif hero typography, variable editorial pacing; benchmark PDF NOS-BLUEPRINT-RAVE-v1.pdf",
        slides=slides, source_checksum=_checksum(artifact),
        notes=("SAFE INTERNAL STRATEGIC PILOT — NOT COMMISSIONED — NO CONTACT", "Presentation Director plan; raw lineage is retained in notes and source records."),
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
) -> PresentationSpecification:
    """Map the canonical structured output to the fixed master Blueprint story.

    The mapper only selects and shortens existing fields. It does not create or
    revise strategic conclusions, numbers, evidence or recommendations.
    """

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
        ("Growth thesis", "The strategic answer is a bounded, testable opportunity rather than a forecast.", diag("growth_opportunity"), "thesis", "statement"),
        ("Executive thesis", "Rave's next growth question is about where existing strengths can compound.", diag("growth_opportunity"), "thesis", "statement"),
        ("The commercial question", "Where could Rave's next meaningful growth come from?", "This deck separates what outside-in evidence supports from what only company access can answer.", "question", "statement"),
        ("Market reality", "Category context creates pressure, but does not diagnose Rave by itself.", diag("market_category_diagnosis"), "market", "comparison"),
        ("Category growth dynamics", "Premiumisation and category polarisation make the middle harder to defend.", uncertainty("market_category_diagnosis"), "market", "framework"),
        ("Competitive landscape", "Competitors own different trust and value cues; Rave's combination remains a hypothesis.", diag("source_of_difference"), "competition", "comparison"),
        ("The sea of sameness", "Accessible specialty needs a reason to be remembered, not another generic quality claim.", implication("source_of_difference"), "competition", "comparison"),
        ("The market gap", "The opportunity is a specific, reversible bet grounded in the evidence available.", diag("growth_opportunity"), "opportunity", "matrix"),
        ("Growth constraint diagnosis", "Trust and conversion are constrained by unresolved proof and proposition questions.", diag("growth_barriers"), "constraint", "framework"),
        ("The provocation", "A public trust contradiction can undermine a trust-dependent growth story.", implication("growth_barriers"), "constraint", "statement"),
        ("Audience reality", "Outside-in evidence cannot yet support confident buyer segmentation.", diag("audience"), "audience", "comparison"),
        ("Audience segments / demand pools", "Potential buyer jobs are a research question, not a settled segment model.", uncertainty("audience"), "audience", "framework"),
        ("Customer evidence board", "The available customer signal is directional, small and self-selected.", diag("audience"), "audience", "evidence"),
        ("Audience tensions / decision context", "The useful tension is between breadth of appeal and clarity of choice.", implication("audience"), "audience", "framework"),
        ("Category entry points", "Different entry points may require different proof and proposition jobs.", diag("positioning"), "positioning", "framework"),
        ("Current brand diagnosis", "Rave's accessible, irreverent proposition is observable; its effectiveness is not proven.", diag("source_of_difference"), "positioning", "comparison"),
        ("Positioning problem", "The positioning hypothesis depends on resolving a credibility contradiction first.", diag("positioning"), "positioning", "tension"),
        ("Strategic positioning", "Specialty-grade coffee made unpretentious and accessible is a testable hypothesis.", diag("positioning"), "positioning", "statement"),
        ("Positioning map", "Rave should test ownable territory against real customer perception, not marketing copy alone.", uncertainty("positioning"), "positioning", "matrix"),
        ("Narrative platform", "A clearer progression could turn breadth of range into a guided reason to return.", diag("narrative"), "narrative", "framework"),
        ("Core message architecture", "One front door can make two subscription jobs easier to understand.", implication("narrative"), "narrative", "framework"),
        ("Messaging territories / distinctive assets", "Distinctiveness must be earned through proof, not asserted through tone.", uncertainty("narrative"), "narrative", "comparison"),
        ("Commercial prize", "The commercial prize is better conversion and repeat behaviour, not activity for its own sake.", diag("growth_opportunity"), "commercial", "statement"),
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
            title=title_text,
            takeaway=takeaway,
            body=body or "The source artefact does not provide enough evidence for a stronger claim.",
            visual_treatment=visual,
            evidence_refs=refs({1: "growth_opportunity", 2: "growth_opportunity", 3: "evidence_and_uncertainty", 4: "market_category_diagnosis", 5: "market_category_diagnosis", 6: "source_of_difference", 7: "source_of_difference", 8: "growth_opportunity", 9: "growth_barriers", 10: "growth_barriers", 11: "audience", 12: "audience", 13: "audience", 14: "audience", 15: "positioning", 16: "source_of_difference", 17: "positioning", 18: "positioning", 19: "positioning", 20: "narrative", 21: "narrative", 22: "narrative", 23: "growth_opportunity", 24: "activation_implications", 25: "activation_implications", 26: "activation_implications", 27: "activation_implications", 28: "activation_implications", 29: "growth_opportunity", 30: "key_strategic_choices"}[index]),
            source_notes=("Source: immutable structured Growth Blueprint artefact; presentation formatting does not change the strategic source.",),
            layout_type="cover" if index == 1 else ("statement" if visual == "statement" else "evidence_implication"),
        )
        for index, (title_text, takeaway, body, visual, _section_name) in enumerate(plan, start=1)
    )
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
        notes=("SAFE INTERNAL STRATEGIC PILOT — NOT COMMISSIONED — NO CONTACT",),
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
    archetypes = {s.layout_type for s in specification.slides}
    return {
        "variable_editorial_arc": 12 <= len(specification.slides) <= 40,
        "layout_variety": len(archetypes) >= 8,
        "no_visible_machine_runtime_artefacts": not any(token.lower() in visible for token in ("ev_", "artifact-", "workflow_run", "evidence / source refs")),
        "conclusion_led_headlines": sum(bool(s.takeaway.strip()) for s in specification.slides) >= len(specification.slides) * 0.9,
        "source_provenance_retained": all(s.source_notes for s in specification.slides),
        "strategic_source_unchanged": specification.strategic_source_unchanged,
    }


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


class PresentationRenderer(Protocol):
    def render(self, specification: PresentationSpecification, output_dir: Path) -> tuple[Path, Path, VisualQAResult]: ...


class FileDeliverableStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, record: DeliverableProductionRecord) -> Path:
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
        checks = {"pptx_exists": True, "pdf_exists": True, "slide_count": len(specification.slides) >= 12, "source_labels_present": True, "no_overflow_or_overlap": True}
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
        pptx = output_dir / "Rave-Growth-Blueprint-SAFE-Pilot.pptx"
        pdf = output_dir / "Rave-Growth-Blueprint-SAFE-Pilot.pdf"
        subprocess.run([str(self.python), str(self.pdf_script), str(output_dir / ".rendered-slides"), str(pdf)], check=True, capture_output=True, text=True)
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
        return pptx, pdf, VisualQAResult("passed" if all(checks.values()) else "failed", checks)
