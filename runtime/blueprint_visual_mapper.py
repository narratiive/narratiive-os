from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .blueprint_knowledge_registry import BlueprintKnowledgeAsset, BlueprintKnowledgeRegistry, BlueprintCanonBundle
from .blueprint_orchestrator import (
    BlueprintLineage,
    BlueprintSlide,
    SlideContent,
    SourceNote,
    StructuredBlueprint,
    ValidationFinding,
    EvidenceReference,
)
from .research_engine import sha256_hex, utc_now


REPO_ROOT = Path(__file__).resolve().parents[1]
VISUAL_LIBRARY_ASSET_ID = "visual_framework_library_v1"
VISUAL_INTELLIGENCE_ASSET_ID = "visual_intelligence_system_v1"
SCHEMA_ASSET_ID = "blueprint_schema_v3"


def _stable_json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalise_label(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def _normalise_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    token = re.sub(r"\b(the|and|or|of|for|to|a|an|in|on|with|via|from|by|we|our|current|next|core|system|framework|page|slide)\b", " ", token)
    return re.sub(r"\s+", " ", token).strip()


def _tokenise(value: str) -> set[str]:
    return {token for token in _normalise_token(value).split() if token}


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return tuple(values)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", str(text)))


def _paragraphs(text: str) -> tuple[str, ...]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current).strip())
    return tuple(item for item in paragraphs if item)


def _parse_key_value_block(lines: Sequence[str]) -> dict[str, list[str]]:
    payload: dict[str, list[str]] = {}
    current_key = ""
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        match = re.match(r"^(?P<key>[A-Za-z0-9 /()#-]+):\s*(?P<value>.*\S)?\s*$", line)
        if match:
            current_key = match.group("key").strip()
            value = match.group("value") or ""
            payload.setdefault(current_key, []).append(value.strip())
            continue
        if current_key:
            payload.setdefault(current_key, []).append(line.strip())
    return payload


def _count_tokens(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokenise(value))
    return tokens


def _split_csv(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    parts: list[str] = []
    for chunk in re.split(r"[,;\n]", str(text)):
        item = chunk.strip()
        if not item:
            continue
        if item not in parts:
            parts.append(item)
    return tuple(parts)


def _parse_used_on(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    items: list[str] = []
    for value in values:
        for part in re.split(r"[,;\n]", str(value)):
            item = part.strip()
            if not item:
                continue
            if item not in items:
                items.append(item)
    return tuple(items)


def _extract_framework_hints(
    framework_name: str,
    purpose: str,
    inputs: Sequence[str],
    outputs: Sequence[str],
    structural_rules: Sequence[str],
) -> tuple[str, ...]:
    hints: list[str] = []
    sources = (
        framework_name,
        purpose,
        " ".join(inputs),
        " ".join(outputs),
        " ".join(structural_rules),
    )
    for source in sources:
        label = _normalise_label(source)
        if label and label not in hints:
            hints.append(label)
        tokens = [token for token in _normalise_token(source).split() if token]
        if not tokens:
            continue
        phrase = " ".join(tokens)
        if phrase and phrase not in hints:
            hints.append(phrase)
        if len(tokens) > 1:
            for token in tokens:
                if len(token) > 3 and token not in hints:
                    hints.append(token)
    return tuple(hints)


@dataclass(frozen=True, slots=True)
class RenderValidationFinding:
    code: str
    severity: str
    message: str
    location: str = ""
    evidence_ids: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        severity = str(self.severity).strip().lower()
        if severity not in {"info", "warning", "error", "blocking"}:
            raise ValueError("severity must be info, warning, error, or blocking")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(
            self,
            "evidence_ids",
            _unique(str(item) for item in self.evidence_ids if str(item).strip()),
        )
        object.__setattr__(self, "details", dict(self.details or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "evidence_ids": list(self.evidence_ids),
            "details": dict(self.details),
        }

    @property
    def is_blocking(self) -> bool:
        return self.severity == "blocking"


@dataclass(frozen=True, slots=True)
class LayoutSpecification:
    layout_type: str
    layout_name: str
    summary: str
    regions: tuple[str, ...]
    geometry: tuple[str, ...]
    copy_density_limit_words: int | None = None
    paragraph_limit_words: int | None = None
    bullet_limit: int | None = None
    supported_framework_ids: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "layout_type", str(self.layout_type).strip())
        object.__setattr__(self, "layout_name", str(self.layout_name).strip())
        object.__setattr__(self, "summary", str(self.summary).strip())
        object.__setattr__(self, "regions", _unique(self.regions))
        object.__setattr__(self, "geometry", _unique(self.geometry))
        object.__setattr__(self, "supported_framework_ids", _unique(self.supported_framework_ids))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_type": self.layout_type,
            "layout_name": self.layout_name,
            "summary": self.summary,
            "regions": list(self.regions),
            "geometry": list(self.geometry),
            "copy_density_limit_words": self.copy_density_limit_words,
            "paragraph_limit_words": self.paragraph_limit_words,
            "bullet_limit": self.bullet_limit,
            "supported_framework_ids": list(self.supported_framework_ids),
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class VisualFrameworkDefinition:
    framework_id: str
    framework_name: str
    source_asset_id: str
    source_title: str
    source_path: str
    source_checksum: str
    source_modified_at: str
    source_kind: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    structural_rules: tuple[str, ...]
    visual_type_aliases: tuple[str, ...] = ()
    used_on: tuple[str, ...] = ()
    layout_types: tuple[str, ...] = ()
    selection_hints: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "framework_id", str(self.framework_id).strip())
        object.__setattr__(self, "framework_name", str(self.framework_name).strip())
        object.__setattr__(self, "source_asset_id", str(self.source_asset_id).strip())
        object.__setattr__(self, "source_title", str(self.source_title).strip())
        object.__setattr__(self, "source_path", str(self.source_path).strip())
        object.__setattr__(self, "source_checksum", str(self.source_checksum).strip())
        object.__setattr__(self, "source_modified_at", str(self.source_modified_at).strip())
        object.__setattr__(self, "source_kind", str(self.source_kind).strip())
        object.__setattr__(self, "purpose", str(self.purpose).strip())
        object.__setattr__(self, "inputs", _unique(self.inputs))
        object.__setattr__(self, "outputs", _unique(self.outputs))
        object.__setattr__(self, "structural_rules", _unique(self.structural_rules))
        object.__setattr__(self, "visual_type_aliases", _unique(self.visual_type_aliases))
        object.__setattr__(self, "used_on", _unique(self.used_on))
        object.__setattr__(self, "layout_types", _unique(self.layout_types))
        object.__setattr__(self, "selection_hints", _unique(self.selection_hints))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_id": self.framework_id,
            "framework_name": self.framework_name,
            "source_asset_id": self.source_asset_id,
            "source_title": self.source_title,
            "source_path": self.source_path,
            "source_checksum": self.source_checksum,
            "source_modified_at": self.source_modified_at,
            "source_kind": self.source_kind,
            "purpose": self.purpose,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "structural_rules": list(self.structural_rules),
            "visual_type_aliases": list(self.visual_type_aliases),
            "used_on": list(self.used_on),
            "layout_types": list(self.layout_types),
            "selection_hints": list(self.selection_hints),
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class VisualFrameworkSelection:
    slide_no: int
    slide_name: str
    act: str
    framework_id: str
    framework_name: str
    source_kind: str
    selected_visual_type: str
    selected_layout_type: str
    selection_reason: str
    confidence: float
    candidate_framework_ids: tuple[str, ...] = ()
    matched_aliases: tuple[str, ...] = ()
    layout_spec: LayoutSpecification | None = None
    validation_findings: tuple[RenderValidationFinding, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "slide_no", int(self.slide_no))
        object.__setattr__(self, "slide_name", str(self.slide_name).strip())
        object.__setattr__(self, "act", str(self.act).strip())
        object.__setattr__(self, "framework_id", str(self.framework_id).strip())
        object.__setattr__(self, "framework_name", str(self.framework_name).strip())
        object.__setattr__(self, "source_kind", str(self.source_kind).strip())
        object.__setattr__(self, "selected_visual_type", str(self.selected_visual_type).strip())
        object.__setattr__(self, "selected_layout_type", str(self.selected_layout_type).strip())
        object.__setattr__(self, "selection_reason", str(self.selection_reason).strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "candidate_framework_ids", _unique(self.candidate_framework_ids))
        object.__setattr__(self, "matched_aliases", _unique(self.matched_aliases))
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_no": self.slide_no,
            "slide_name": self.slide_name,
            "act": self.act,
            "framework_id": self.framework_id,
            "framework_name": self.framework_name,
            "source_kind": self.source_kind,
            "selected_visual_type": self.selected_visual_type,
            "selected_layout_type": self.selected_layout_type,
            "selection_reason": self.selection_reason,
            "confidence": self.confidence,
            "candidate_framework_ids": list(self.candidate_framework_ids),
            "matched_aliases": list(self.matched_aliases),
            "layout_spec": self.layout_spec.to_dict() if self.layout_spec is not None else None,
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class ContentBlock:
    block_type: str
    text: str
    order: int
    placement: str = ""
    evidence_ids: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_type", str(self.block_type).strip())
        object.__setattr__(self, "text", str(self.text).strip())
        object.__setattr__(self, "order", int(self.order))
        object.__setattr__(self, "placement", str(self.placement).strip())
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_type": self.block_type,
            "text": self.text,
            "order": self.order,
            "placement": self.placement,
            "evidence_ids": list(self.evidence_ids),
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class EvidenceBlock(ContentBlock):
    source_note: str = ""
    slide_no: int | None = None
    slide_name: str = ""
    claim: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        ContentBlock.__post_init__(self)
        object.__setattr__(self, "source_note", str(self.source_note).strip())
        object.__setattr__(self, "slide_no", None if self.slide_no is None else int(self.slide_no))
        object.__setattr__(self, "slide_name", str(self.slide_name).strip())
        object.__setattr__(self, "claim", str(self.claim).strip())
        object.__setattr__(self, "confidence", float(self.confidence))

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "source_note": self.source_note,
                "slide_no": self.slide_no,
                "slide_name": self.slide_name,
                "claim": self.claim,
                "confidence": self.confidence,
            }
        )
        return data


@dataclass(frozen=True, slots=True)
class FounderInsightBlock(ContentBlock):
    pass


@dataclass(frozen=True, slots=True)
class SoWhatBlock(ContentBlock):
    pass


@dataclass(frozen=True, slots=True)
class SourceNoteBlock(ContentBlock):
    source_note: str = ""

    def __post_init__(self) -> None:
        ContentBlock.__post_init__(self)
        object.__setattr__(self, "source_note", str(self.source_note).strip())

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["source_note"] = self.source_note
        return data


@dataclass(frozen=True, slots=True)
class SpeakerNoteBlock(ContentBlock):
    pass


@dataclass(frozen=True, slots=True)
class RenderLineage:
    structured_blueprint: BlueprintLineage
    structured_blueprint_id: str
    structured_blueprint_version: int
    structured_blueprint_outline_hash: str
    structured_blueprint_checksum: str
    registry_id: str
    registry_version: str
    registry_checksum: str
    canon_bundle: BlueprintCanonBundle
    source_asset_ids: tuple[str, ...]
    source_asset_checksums: tuple[str, ...]
    source_asset_paths: tuple[str, ...]
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "structured_blueprint_id", str(self.structured_blueprint_id).strip())
        object.__setattr__(self, "structured_blueprint_version", int(self.structured_blueprint_version))
        object.__setattr__(self, "structured_blueprint_outline_hash", str(self.structured_blueprint_outline_hash).strip())
        object.__setattr__(self, "structured_blueprint_checksum", str(self.structured_blueprint_checksum).strip())
        object.__setattr__(self, "registry_id", str(self.registry_id).strip())
        object.__setattr__(self, "registry_version", str(self.registry_version).strip())
        object.__setattr__(self, "registry_checksum", str(self.registry_checksum).strip())
        object.__setattr__(self, "source_asset_ids", _unique(self.source_asset_ids))
        object.__setattr__(self, "source_asset_checksums", _unique(self.source_asset_checksums))
        object.__setattr__(self, "source_asset_paths", _unique(self.source_asset_paths))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "structured_blueprint": self.structured_blueprint.to_dict(),
            "structured_blueprint_id": self.structured_blueprint_id,
            "structured_blueprint_version": self.structured_blueprint_version,
            "structured_blueprint_outline_hash": self.structured_blueprint_outline_hash,
            "structured_blueprint_checksum": self.structured_blueprint_checksum,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "registry_checksum": self.registry_checksum,
            "canon_bundle": self.canon_bundle.to_dict(),
            "source_asset_ids": list(self.source_asset_ids),
            "source_asset_checksums": list(self.source_asset_checksums),
            "source_asset_paths": list(self.source_asset_paths),
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class RenderableSlide:
    slide_no: int
    slide_name: str
    act: str
    framework_selection: VisualFrameworkSelection
    selected_framework_id: str
    selected_visual_type: str
    selected_layout_type: str
    content_blocks: tuple[ContentBlock, ...]
    evidence_blocks: tuple[EvidenceBlock, ...]
    founder_insight_blocks: tuple[FounderInsightBlock, ...]
    so_what_blocks: tuple[SoWhatBlock, ...]
    source_note_blocks: tuple[SourceNoteBlock, ...]
    speaker_note_blocks: tuple[SpeakerNoteBlock, ...]
    visual_hierarchy: tuple[str, ...]
    evidence_placement: str
    founder_insight_placement: str
    so_what_placement: str
    source_note_treatment: str
    speaker_notes: tuple[str, ...]
    chart_or_diagram_intent: str
    geometry_regions: tuple[str, ...]
    design_token_references: tuple[str, ...]
    validation_findings: tuple[RenderValidationFinding, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "slide_no", int(self.slide_no))
        object.__setattr__(self, "slide_name", str(self.slide_name).strip())
        object.__setattr__(self, "act", str(self.act).strip())
        object.__setattr__(self, "selected_framework_id", str(self.selected_framework_id).strip())
        object.__setattr__(self, "selected_visual_type", str(self.selected_visual_type).strip())
        object.__setattr__(self, "selected_layout_type", str(self.selected_layout_type).strip())
        object.__setattr__(self, "content_blocks", tuple(self.content_blocks))
        object.__setattr__(self, "evidence_blocks", tuple(self.evidence_blocks))
        object.__setattr__(self, "founder_insight_blocks", tuple(self.founder_insight_blocks))
        object.__setattr__(self, "so_what_blocks", tuple(self.so_what_blocks))
        object.__setattr__(self, "source_note_blocks", tuple(self.source_note_blocks))
        object.__setattr__(self, "speaker_note_blocks", tuple(self.speaker_note_blocks))
        object.__setattr__(self, "visual_hierarchy", _unique(self.visual_hierarchy))
        object.__setattr__(self, "evidence_placement", str(self.evidence_placement).strip())
        object.__setattr__(self, "founder_insight_placement", str(self.founder_insight_placement).strip())
        object.__setattr__(self, "so_what_placement", str(self.so_what_placement).strip())
        object.__setattr__(self, "source_note_treatment", str(self.source_note_treatment).strip())
        object.__setattr__(self, "speaker_notes", _unique(self.speaker_notes))
        object.__setattr__(self, "chart_or_diagram_intent", str(self.chart_or_diagram_intent).strip())
        object.__setattr__(self, "geometry_regions", _unique(self.geometry_regions))
        object.__setattr__(self, "design_token_references", _unique(self.design_token_references))
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_no": self.slide_no,
            "slide_name": self.slide_name,
            "act": self.act,
            "framework_selection": self.framework_selection.to_dict(),
            "selected_framework_id": self.selected_framework_id,
            "selected_visual_type": self.selected_visual_type,
            "selected_layout_type": self.selected_layout_type,
            "content_blocks": [block.to_dict() for block in self.content_blocks],
            "evidence_blocks": [block.to_dict() for block in self.evidence_blocks],
            "founder_insight_blocks": [block.to_dict() for block in self.founder_insight_blocks],
            "so_what_blocks": [block.to_dict() for block in self.so_what_blocks],
            "source_note_blocks": [block.to_dict() for block in self.source_note_blocks],
            "speaker_note_blocks": [block.to_dict() for block in self.speaker_note_blocks],
            "visual_hierarchy": list(self.visual_hierarchy),
            "evidence_placement": self.evidence_placement,
            "founder_insight_placement": self.founder_insight_placement,
            "so_what_placement": self.so_what_placement,
            "source_note_treatment": self.source_note_treatment,
            "speaker_notes": list(self.speaker_notes),
            "chart_or_diagram_intent": self.chart_or_diagram_intent,
            "geometry_regions": list(self.geometry_regions),
            "design_token_references": list(self.design_token_references),
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class RenderableAct:
    act_no: int
    act_name: str
    slides: tuple[RenderableSlide, ...]
    validation_findings: tuple[RenderValidationFinding, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "act_no", int(self.act_no))
        object.__setattr__(self, "act_name", str(self.act_name).strip())
        object.__setattr__(self, "slides", tuple(self.slides))
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "act_no": self.act_no,
            "act_name": self.act_name,
            "slides": [slide.to_dict() for slide in self.slides],
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class RenderableBlueprint:
    blueprint_id: str
    blueprint_version: int
    request_id: str
    workspace_id: str
    client_id: str
    acts: tuple[RenderableAct, ...]
    lineage: RenderLineage
    validation_findings: tuple[RenderValidationFinding, ...]
    status: str
    confidence: float
    created_at: str = field(default_factory=utc_now)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "blueprint_id", str(self.blueprint_id).strip())
        object.__setattr__(self, "blueprint_version", int(self.blueprint_version))
        object.__setattr__(self, "request_id", str(self.request_id).strip())
        object.__setattr__(self, "workspace_id", str(self.workspace_id).strip())
        object.__setattr__(self, "client_id", str(self.client_id).strip())
        object.__setattr__(self, "acts", tuple(self.acts))
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "status", str(self.status).strip().lower())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    @property
    def sections(self) -> tuple[RenderableAct, ...]:
        return self.acts

    @property
    def slides(self) -> tuple[RenderableSlide, ...]:
        return tuple(slide for act in self.acts for slide in act.slides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "acts": [act.to_dict() for act in self.acts],
            "sections": [act.to_dict() for act in self.acts],
            "slides": [slide.to_dict() for slide in self.slides],
            "lineage": self.lineage.to_dict(),
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "status": self.status,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class _FrameworkParserResult:
    frameworks: tuple[VisualFrameworkDefinition, ...]
    layout_specs: dict[str, LayoutSpecification]
    design_tokens: dict[str, Any]
    registry_checksum: str
    registry_version: str
    extensions: dict[str, Any] = field(default_factory=dict)


class VisualFrameworkRegistry:
    def __init__(
        self,
        *,
        knowledge_registry: BlueprintKnowledgeRegistry,
        frameworks: Sequence[VisualFrameworkDefinition],
        layout_specs: Mapping[str, LayoutSpecification],
        design_tokens: Mapping[str, Any],
        registry_version: str,
        registry_checksum: str,
        extensions: Mapping[str, Any] | None = None,
    ) -> None:
        self.knowledge_registry = knowledge_registry
        self.frameworks = tuple(frameworks)
        self.layout_specs = dict(layout_specs)
        self.design_tokens = dict(design_tokens)
        self.registry_version = str(registry_version).strip()
        self.registry_checksum = str(registry_checksum).strip()
        self.extensions = dict(extensions or {})
        self._definitions_by_id = {definition.framework_id: definition for definition in self.frameworks}
        self._aliases: dict[str, set[str]] = {}
        for definition in self.frameworks:
            self._register_alias(definition.framework_id, definition.framework_id)
            self._register_alias(definition.framework_name, definition.framework_id)
            self._register_alias(definition.source_title, definition.framework_id)
            for alias in definition.visual_type_aliases:
                self._register_alias(alias, definition.framework_id)
            for alias in definition.selection_hints:
                self._register_alias(alias, definition.framework_id)

    @classmethod
    def from_knowledge_registry(cls, knowledge_registry: BlueprintKnowledgeRegistry) -> "VisualFrameworkRegistry":
        framework_asset = knowledge_registry.asset(VISUAL_LIBRARY_ASSET_ID)
        intelligence_asset = knowledge_registry.asset(VISUAL_INTELLIGENCE_ASSET_ID)
        schema_asset = knowledge_registry.asset(SCHEMA_ASSET_ID)
        parsed = _parse_visual_registry(
            knowledge_registry=knowledge_registry,
            framework_asset=framework_asset,
            intelligence_asset=intelligence_asset,
            schema_asset=schema_asset,
        )
        return cls(
            knowledge_registry=knowledge_registry,
            frameworks=parsed.frameworks,
            layout_specs=parsed.layout_specs,
            design_tokens=parsed.design_tokens,
            registry_version=parsed.registry_version,
            registry_checksum=parsed.registry_checksum,
            extensions=parsed.extensions,
        )

    def _register_alias(self, alias: str, framework_id: str) -> None:
        normalised = _normalise_label(alias)
        if not normalised:
            return
        self._aliases.setdefault(normalised, set()).add(framework_id)

    def definition(self, framework_id: str) -> VisualFrameworkDefinition:
        key = _normalise_label(framework_id)
        if key in self._definitions_by_id:
            return self._definitions_by_id[key]
        alias_ids = self._aliases.get(key)
        if not alias_ids:
            raise KeyError(f"unknown visual framework: {framework_id}")
        if len(alias_ids) > 1:
            raise ValueError(f"ambiguous visual framework alias: {framework_id}")
        return self._definitions_by_id[next(iter(alias_ids))]

    def layout(self, layout_type: str) -> LayoutSpecification:
        layout_type = str(layout_type).strip().upper()
        try:
            return self.layout_specs[layout_type]
        except KeyError as exc:
            raise KeyError(f"unknown layout type: {layout_type}") from exc

    def all_definitions(self) -> tuple[VisualFrameworkDefinition, ...]:
        return self.frameworks

    def select(self, slide: BlueprintSlide) -> VisualFrameworkSelection:
        candidates: list[tuple[float, VisualFrameworkDefinition, tuple[str, ...], str]] = []
        slide_tokens = _count_tokens(slide.slide_name, slide.purpose, slide.visual_type, " ".join(slide.content_requirements))
        for definition in self.frameworks:
            reason_bits: list[str] = []
            score = 0.0
            if _normalise_label(slide.visual_type) == _normalise_label(definition.framework_id):
                score += 120
                reason_bits.append("visual_type")
            alias_matches = []
            for alias in (definition.visual_type_aliases + definition.selection_hints + (definition.framework_name, definition.source_title)):
                if _normalise_label(slide.visual_type) == _normalise_label(alias):
                    score += 100
                    alias_matches.append(alias)
            if _normalise_label(slide.slide_name) == _normalise_label(definition.framework_name):
                score += 70
                reason_bits.append("slide_name")
            framework_tokens = _count_tokens(
                definition.framework_name,
                definition.purpose,
                " ".join(definition.inputs),
                " ".join(definition.outputs),
                " ".join(definition.structural_rules),
                " ".join(definition.selection_hints),
            )
            overlap = slide_tokens & framework_tokens
            if overlap:
                score += 12 * len(overlap)
                reason_bits.append(f"overlap:{','.join(sorted(overlap))}")
            if definition.source_kind != "schema":
                score += 8
            if definition.source_kind == "schema":
                score += 4
            if slide.layout_type and slide.layout_type in definition.layout_types:
                score += 18
                reason_bits.append("layout")
            if definition.used_on:
                used_tokens = _count_tokens(" ".join(definition.used_on))
                used_overlap = used_tokens & slide_tokens
                if used_overlap:
                    score += 10 * len(used_overlap)
                    reason_bits.append(f"used_on:{','.join(sorted(used_overlap))}")
            if not reason_bits:
                reason_bits.append("schema_fallback")
            candidates.append((score, definition, tuple(alias_matches), ";".join(reason_bits)))

        candidates.sort(key=lambda item: (item[0], item[1].framework_id), reverse=True)
        top_score = candidates[0][0]
        top_candidates = [item for item in candidates if item[0] == top_score and top_score > 0]
        if len(top_candidates) > 1:
            top_ids = {item[1].framework_id for item in top_candidates}
            if len(top_ids) > 1 and top_score >= 60:
                raise BlueprintVisualMappingError(
                    f"ambiguous visual framework mapping for slide {slide.slide_no}: {sorted(top_ids)}"
                )

        score, definition, alias_matches, reason = candidates[0]
        layout_spec = self.layout(slide.layout_type)
        validations: list[RenderValidationFinding] = []
        if layout_spec.layout_type not in {"A", "B", "C", "D", "E", "F"}:
            validations.append(
                RenderValidationFinding(
                    code="unsupported_layout_type",
                    severity="blocking",
                    message="The layout type is not supported by the Canon.",
                    location=f"slide.{slide.slide_no}",
                    details={"layout_type": slide.layout_type},
                )
            )
        if not definition.inputs and not definition.outputs:
            validations.append(
                RenderValidationFinding(
                    code="missing_framework_inputs",
                    severity="warning",
                    message="The framework registry did not expose explicit inputs or outputs.",
                    location=f"slide.{slide.slide_no}",
                )
            )
        return VisualFrameworkSelection(
            slide_no=slide.slide_no,
            slide_name=slide.slide_name,
            act=slide.act,
            framework_id=definition.framework_id,
            framework_name=definition.framework_name,
            source_kind=definition.source_kind,
            selected_visual_type=slide.visual_type,
            selected_layout_type=slide.layout_type,
            selection_reason=reason,
            confidence=_selection_confidence(score),
            candidate_framework_ids=tuple(sorted({candidate[1].framework_id for candidate in candidates})),
            matched_aliases=alias_matches,
            layout_spec=layout_spec,
            validation_findings=tuple(validations),
            extensions={
                "definition": definition.to_dict(),
                "selection_score": score,
                "candidate_scores": [
                    {"framework_id": candidate[1].framework_id, "score": candidate[0], "reason": candidate[3]}
                    for candidate in candidates[:5]
                ],
            },
        )


class BlueprintVisualMappingError(RuntimeError):
    pass


class BlueprintVisualMapper:
    def __init__(
        self,
        knowledge_registry: BlueprintKnowledgeRegistry | None = None,
        framework_registry: VisualFrameworkRegistry | None = None,
    ) -> None:
        self.knowledge_registry = knowledge_registry or BlueprintKnowledgeRegistry.from_default()
        self.framework_registry = framework_registry or VisualFrameworkRegistry.from_knowledge_registry(self.knowledge_registry)

    def map(self, structured_blueprint: StructuredBlueprint) -> RenderableBlueprint:
        self._validate_workspace(structured_blueprint)
        act_nodes: list[RenderableAct] = []
        findings: list[RenderValidationFinding] = []
        for act in structured_blueprint.acts:
            slides: list[RenderableSlide] = []
            act_findings: list[RenderValidationFinding] = []
            for slide in act.slides:
                selection = self.framework_registry.select(slide)
                slide_renderable, slide_findings = self._render_slide(structured_blueprint, slide, selection)
                slides.append(slide_renderable)
                findings.extend(slide_findings)
                act_findings.extend(slide_findings)
            act_nodes.append(
                RenderableAct(
                    act_no=act.act_no,
                    act_name=act.act_name,
                    slides=tuple(slides),
                    validation_findings=tuple(act_findings),
                    extensions={
                        "schema_slide_numbers": [slide.slide_no for slide in slides],
                        "source_act_name": act.source_act_name,
                    },
                )
            )

        render_status = "invalid" if any(finding.severity in {"error", "blocking"} for finding in findings) else "complete"
        confidence = _confidence_from_findings(findings)
        lineage = self._lineage(structured_blueprint)
        return RenderableBlueprint(
            blueprint_id=structured_blueprint.blueprint_id,
            blueprint_version=structured_blueprint.blueprint_version,
            request_id=structured_blueprint.request_id,
            workspace_id=structured_blueprint.workspace_id,
            client_id=structured_blueprint.client_id,
            acts=tuple(act_nodes),
            lineage=lineage,
            validation_findings=tuple(findings),
            status=render_status,
            confidence=confidence,
            created_at=utc_now(),
            extensions=dict(structured_blueprint.extensions),
        )

    def _lineage(self, structured_blueprint: StructuredBlueprint) -> RenderLineage:
        source_assets = self._source_assets()
        return RenderLineage(
            structured_blueprint=structured_blueprint.lineage,
            structured_blueprint_id=structured_blueprint.blueprint_id,
            structured_blueprint_version=structured_blueprint.blueprint_version,
            structured_blueprint_outline_hash=structured_blueprint.outline_hash,
            structured_blueprint_checksum=sha256_hex(_stable_json(structured_blueprint.to_dict())),
            registry_id="blueprint_visual_framework_registry",
            registry_version=self.framework_registry.registry_version,
            registry_checksum=self.framework_registry.registry_checksum,
            canon_bundle=structured_blueprint.canon_bundle,
            source_asset_ids=tuple(asset.asset_id for asset in source_assets),
            source_asset_checksums=tuple(asset.checksum for asset in source_assets),
            source_asset_paths=tuple(asset.repository_path for asset in source_assets),
        )

    def _source_assets(self) -> tuple[BlueprintKnowledgeAsset, ...]:
        return (
            self.knowledge_registry.asset(VISUAL_LIBRARY_ASSET_ID),
            self.knowledge_registry.asset(VISUAL_INTELLIGENCE_ASSET_ID),
            self.knowledge_registry.asset(SCHEMA_ASSET_ID),
        )

    def _validate_workspace(self, structured_blueprint: StructuredBlueprint) -> None:
        if not structured_blueprint.workspace_id:
            raise BlueprintVisualMappingError("structured blueprint workspace is missing")
        if structured_blueprint.lineage.canon_bundle.bundle_id != "blueprint-canon-v1":
            raise BlueprintVisualMappingError("unexpected canon bundle for visual mapping")

    def _render_slide(
        self,
        structured_blueprint: StructuredBlueprint,
        slide: BlueprintSlide,
        selection: VisualFrameworkSelection,
    ) -> tuple[RenderableSlide, tuple[RenderValidationFinding, ...]]:
        findings: list[RenderValidationFinding] = list(selection.validation_findings)
        content_blocks, block_findings = self._content_blocks(slide)
        findings.extend(block_findings)
        if not selection.framework_id:
            findings.append(
                RenderValidationFinding(
                    code="missing_framework_selection",
                    severity="blocking",
                    message="Every slide must map to exactly one visual framework.",
                    location=f"slide.{slide.slide_no}",
                )
            )

        layout = selection.layout_spec or self.framework_registry.layout(slide.layout_type)
        evidence_ids = self._evidence_ids_from_blocks(content_blocks)
        if self._missing_required_input(slide, selection):
            findings.append(
                RenderValidationFinding(
                    code="missing_required_input",
                    severity="blocking",
                    message="The selected framework requires input that is not present on the structured slide.",
                    location=f"slide.{slide.slide_no}",
                    details={"framework_id": selection.framework_id},
                )
            )
        if not slide.so_what:
            findings.append(
                RenderValidationFinding(
                    code="missing_so_what_block",
                    severity="blocking",
                    message="The slide must preserve its So What implication.",
                    location=f"slide.{slide.slide_no}",
                )
            )
        if slide.founder_insight and not any(block.block_type == "founder_insight" for block in content_blocks):
            findings.append(
                RenderValidationFinding(
                    code="missing_founder_insight_block",
                    severity="blocking",
                    message="The slide must preserve Founder Insight placement.",
                    location=f"slide.{slide.slide_no}",
                )
            )
        if slide.content.source_notes and not any(block.block_type == "source_note" for block in content_blocks):
            findings.append(
                RenderValidationFinding(
                    code="missing_source_note_block",
                    severity="blocking",
                    message="The slide must preserve source notes.",
                    location=f"slide.{slide.slide_no}",
                )
            )
        density_findings = self._copy_density_findings(slide, content_blocks, layout)
        findings.extend(density_findings)
        renderable = RenderableSlide(
            slide_no=slide.slide_no,
            slide_name=slide.slide_name,
            act=slide.act,
            framework_selection=selection,
            selected_framework_id=selection.framework_id,
            selected_visual_type=slide.visual_type,
            selected_layout_type=slide.layout_type,
            content_blocks=content_blocks,
            evidence_blocks=tuple(block for block in content_blocks if isinstance(block, EvidenceBlock)),
            founder_insight_blocks=tuple(block for block in content_blocks if isinstance(block, FounderInsightBlock)),
            so_what_blocks=tuple(block for block in content_blocks if isinstance(block, SoWhatBlock)),
            source_note_blocks=tuple(block for block in content_blocks if isinstance(block, SourceNoteBlock)),
            speaker_note_blocks=tuple(block for block in content_blocks if isinstance(block, SpeakerNoteBlock)),
            visual_hierarchy=tuple(block.block_type for block in content_blocks),
            evidence_placement=self._placement_for_layout(slide.layout_type, "evidence"),
            founder_insight_placement=self._placement_for_layout(slide.layout_type, "founder_insight"),
            so_what_placement=self._placement_for_layout(slide.layout_type, "so_what"),
            source_note_treatment=self._source_note_treatment(slide.layout_type),
            speaker_notes=tuple(block.text for block in content_blocks if isinstance(block, SpeakerNoteBlock)),
            chart_or_diagram_intent=self._diagram_intent(selection),
            geometry_regions=tuple(selection.layout_spec.geometry) if selection.layout_spec else (),
            design_token_references=self._design_tokens_for_slide(slide, selection),
            validation_findings=tuple(findings),
            extensions=dict(slide.extensions),
        )
        return renderable, tuple(findings)

    def _content_blocks(self, slide: BlueprintSlide) -> tuple[tuple[ContentBlock, ...], tuple[RenderValidationFinding, ...]]:
        blocks: list[ContentBlock] = []
        findings: list[RenderValidationFinding] = []
        order = 0
        for paragraph in slide.content.thesis:
            blocks.append(
                ContentBlock(
                    block_type="thesis",
                    text=paragraph,
                    order=order,
                    placement="primary_narrative",
                    evidence_ids=self._slide_evidence_ids(slide),
                )
            )
            order += 1
        for paragraph in slide.content.founder_insight:
            blocks.append(
                FounderInsightBlock(
                    block_type="founder_insight",
                    text=paragraph,
                    order=order,
                    placement="insight_callout",
                    evidence_ids=self._slide_evidence_ids(slide),
                )
            )
            order += 1
        for paragraph in slide.content.so_what:
            blocks.append(
                SoWhatBlock(
                    block_type="so_what",
                    text=paragraph,
                    order=order,
                    placement="implication_footer",
                    evidence_ids=self._slide_evidence_ids(slide),
                )
            )
            order += 1
        for note in slide.content.source_notes:
            blocks.append(
                SourceNoteBlock(
                    block_type="source_note",
                    text=note.text,
                    order=order,
                    placement="evidence_rail",
                    evidence_ids=note.evidence_ids,
                    source_note=note.text,
                    extensions=note.extensions,
                )
            )
            order += 1
        for paragraph in slide.content.visual_direction:
            blocks.append(
                ContentBlock(
                    block_type="visual_direction",
                    text=paragraph,
                    order=order,
                    placement="visual_brief",
                    evidence_ids=self._slide_evidence_ids(slide),
                )
            )
            order += 1
        for paragraph in slide.content.speaker_notes:
            blocks.append(
                SpeakerNoteBlock(
                    block_type="speaker_notes",
                    text=paragraph,
                    order=order,
                    placement="presenter_notes",
                    evidence_ids=self._slide_evidence_ids(slide),
                )
            )
            order += 1

        if slide.content.extensions:
            for key, value in slide.content.extensions.items():
                if key == "body":
                    continue
                text = value["body"] if isinstance(value, Mapping) and "body" in value else str(value)
                blocks.append(
                    ContentBlock(
                        block_type=f"extension:{_normalise_label(key).replace(' ', '_')}",
                        text=text,
                        order=order,
                        placement="extension",
                        evidence_ids=self._slide_evidence_ids(slide),
                        extensions={key: value},
                    )
                )
                order += 1

        if slide.content.evidence_references:
            for reference in slide.content.evidence_references:
                blocks.append(
                    EvidenceBlock(
                        block_type="evidence",
                        text=reference.claim or reference.source_note,
                        order=order,
                        placement="evidence_callout",
                        evidence_ids=(reference.evidence_id,),
                        source_note=reference.source_note,
                        slide_no=reference.slide_no,
                        slide_name=reference.slide_name,
                        claim=reference.claim,
                        confidence=reference.confidence,
                        extensions=reference.extensions,
                    )
                )
                order += 1

        if slide.content.extensions.get("body"):
            body_paragraphs = slide.content.extensions["body"]
            if isinstance(body_paragraphs, (list, tuple)):
                for paragraph in body_paragraphs:
                    blocks.append(
                        ContentBlock(
                            block_type="body",
                            text=str(paragraph),
                            order=order,
                            placement="body",
                            evidence_ids=self._slide_evidence_ids(slide),
                        )
                    )
                    order += 1

        if not blocks:
            findings.append(
                RenderValidationFinding(
                    code="empty_renderable_slide",
                    severity="blocking",
                    message="Renderable slides must preserve at least one content block.",
                    location=f"slide.{slide.slide_no}",
                )
            )

        return tuple(blocks), tuple(findings)

    def _slide_evidence_ids(self, slide: BlueprintSlide) -> tuple[str, ...]:
        ids: list[str] = []
        ids.extend(reference.evidence_id for reference in slide.content.evidence_references)
        ids.extend(evidence_id for note in slide.content.source_notes for evidence_id in note.evidence_ids)
        return _unique(ids)

    def _evidence_ids_from_blocks(self, blocks: Sequence[ContentBlock]) -> tuple[str, ...]:
        ids: list[str] = []
        for block in blocks:
            ids.extend(block.evidence_ids)
        return tuple(ids)

    def _missing_required_input(self, slide: BlueprintSlide, selection: VisualFrameworkSelection) -> bool:
        requirement_tokens = _count_tokens(slide.purpose, slide.visual_type, " ".join(slide.content_requirements))
        required_tokens = _count_tokens(selection.framework_name, selection.selection_reason)
        if not required_tokens:
            return False
        return not bool(requirement_tokens & required_tokens)

    def _copy_density_findings(
        self,
        slide: BlueprintSlide,
        blocks: Sequence[ContentBlock],
        layout: LayoutSpecification,
    ) -> tuple[RenderValidationFinding, ...]:
        findings: list[RenderValidationFinding] = []
        visible_blocks = [block for block in blocks if block.block_type not in {"source_note", "speaker_notes"}]
        body_words = sum(_word_count(block.text) for block in visible_blocks)
        if layout.copy_density_limit_words is not None and body_words > layout.copy_density_limit_words:
            findings.append(
                RenderValidationFinding(
                    code="copy_density_exceeded",
                    severity="warning",
                    message="The slide exceeds the copy-density threshold for the Canon.",
                    location=f"slide.{slide.slide_no}",
                    details={"word_count": body_words, "limit": layout.copy_density_limit_words},
                )
            )
        for block in visible_blocks:
            if layout.paragraph_limit_words is not None and _word_count(block.text) > layout.paragraph_limit_words:
                findings.append(
                    RenderValidationFinding(
                        code="paragraph_length_exceeded",
                        severity="warning",
                        message="A content block exceeds the canonical paragraph length.",
                        location=f"slide.{slide.slide_no}",
                        details={"block_type": block.block_type, "word_count": _word_count(block.text)},
                    )
                )
        if layout.bullet_limit is not None:
            bullet_lines = sum(1 for block in visible_blocks for line in block.text.splitlines() if line.strip().startswith(("-", "*", "•")))
            if bullet_lines > layout.bullet_limit:
                findings.append(
                    RenderValidationFinding(
                        code="bullet_limit_exceeded",
                        severity="warning",
                        message="The slide exceeds the canonical bullet limit.",
                        location=f"slide.{slide.slide_no}",
                        details={"bullet_count": bullet_lines, "limit": layout.bullet_limit},
                    )
                )
        return tuple(findings)

    def _placement_for_layout(self, layout_type: str, block_kind: str) -> str:
        layout_type = str(layout_type).strip().upper()
        mapping = {
            "A": {"evidence": "right_rail", "founder_insight": "left_callout", "so_what": "footer"},
            "B": {"evidence": "inline", "founder_insight": "hero_callout", "so_what": "closing_line"},
            "C": {"evidence": "support_column", "founder_insight": "lead_column_callout", "so_what": "footer"},
            "D": {"evidence": "card_support", "founder_insight": "card_header", "so_what": "card_footer"},
            "E": {"evidence": "accent_rail", "founder_insight": "accent_callout", "so_what": "accent_footer"},
            "F": {"evidence": "scorecard_rail", "founder_insight": "plan_callout", "so_what": "decision_footer"},
        }
        return mapping.get(layout_type, {}).get(block_kind, "inline")

    def _source_note_treatment(self, layout_type: str) -> str:
        if layout_type in {"D", "F"}:
            return "compact_evidence_chips"
        if layout_type in {"A", "C"}:
            return "supporting_footnote_rail"
        return "inline_annotation"

    def _diagram_intent(self, selection: VisualFrameworkSelection) -> str:
        framework = selection.framework_name.lower()
        if any(keyword in framework for keyword in ("map", "matrix", "flow", "pyramid", "engine", "ecosystem", "flywheel")):
            return framework
        return selection.selected_visual_type

    def _design_tokens_for_slide(self, slide: BlueprintSlide, selection: VisualFrameworkSelection) -> tuple[str, ...]:
        tokens = [
            "palette.canvas_primary",
            "palette.canvas_secondary",
            "palette.accent_display",
            "palette.accent_section",
            "palette.body",
            "palette.labels",
            "typography.headline",
            "typography.body",
            "typography.label",
            "spacing.breathing_room",
            "hierarchy." + ("section_moment" if slide.layout_type in {"E", "F"} else "body"),
            "line.shape.axis" if any(keyword in selection.framework_name.lower() for keyword in ("map", "matrix")) else "line.shape.card",
        ]
        if slide.layout_type == "F":
            tokens.append("accent.strategic_focus")
        if slide.layout_type == "E":
            tokens.append("accent.pivot")
        return _unique(tokens)


def _selection_confidence(score: float) -> float:
    if score <= 0:
        return 0.1
    return max(0.1, min(1.0, round(score / 120.0, 3)))


def _parse_visual_registry(
    *,
    knowledge_registry: BlueprintKnowledgeRegistry,
    framework_asset: BlueprintKnowledgeAsset,
    intelligence_asset: BlueprintKnowledgeAsset,
    schema_asset: BlueprintKnowledgeAsset,
) -> _FrameworkParserResult:
    framework_text = framework_asset.read_text(knowledge_registry.root)
    intelligence_text = intelligence_asset.read_text(knowledge_registry.root)
    schema = knowledge_registry.schema()
    libraries = _parse_library_frameworks(framework_text, framework_asset, knowledge_registry)
    intelligence_definitions, intelligence_layouts, design_tokens = _parse_intelligence_rules(
        intelligence_text,
        intelligence_asset,
        knowledge_registry,
    )
    schema_definitions = _schema_visual_definitions(schema, schema_asset, knowledge_registry)

    definitions: dict[str, VisualFrameworkDefinition] = {}
    for definition in (*libraries, *intelligence_definitions, *schema_definitions):
        existing = definitions.get(definition.framework_id)
        if existing is None:
            definitions[definition.framework_id] = definition
        else:
            merged = _merge_framework_definitions(existing, definition)
            definitions[definition.framework_id] = merged

    layout_specs = _layout_specs(intelligence_layouts, schema)
    registry_checksum = sha256_hex(
        _stable_json(
            {
                "frameworks": [definition.to_dict() for definition in sorted(definitions.values(), key=lambda item: item.framework_id)],
                "layout_specs": {key: spec.to_dict() for key, spec in sorted(layout_specs.items())},
                "design_tokens": design_tokens,
                "source_assets": {
                    framework_asset.asset_id: framework_asset.checksum,
                    intelligence_asset.asset_id: intelligence_asset.checksum,
                    schema_asset.asset_id: schema_asset.checksum,
                },
            }
        )
    )
    return _FrameworkParserResult(
        frameworks=tuple(sorted(definitions.values(), key=lambda item: item.framework_id)),
        layout_specs=layout_specs,
        design_tokens=design_tokens,
        registry_checksum=registry_checksum,
        registry_version=f"{schema_asset.version}-{framework_asset.version}-{intelligence_asset.version}",
        extensions={
            "source_assets": {
                framework_asset.asset_id: framework_asset.to_dict(),
                intelligence_asset.asset_id: intelligence_asset.to_dict(),
                schema_asset.asset_id: schema_asset.to_dict(),
            },
            "raw_framework_text": framework_text,
            "raw_intelligence_text": intelligence_text,
        },
    )


def _parse_library_frameworks(
    text: str,
    asset: BlueprintKnowledgeAsset,
    knowledge_registry: BlueprintKnowledgeRegistry,
) -> tuple[VisualFrameworkDefinition, ...]:
    sections = _split_on_framework_sections(text)
    definitions: list[VisualFrameworkDefinition] = []
    for section in sections:
        lines = [line.rstrip() for line in section.splitlines() if line.strip()]
        if not lines:
            continue
        heading = lines[0].strip()
        if heading.upper().startswith("TITLE LOCKUP"):
            framework_name = "Title Lockup"
            framework_id = "title_lockup"
            source_kind = "supporting_object"
        elif heading.upper().startswith("CONTACT BLOCK"):
            framework_name = "Contact Block"
            framework_id = "contact_block"
            source_kind = "supporting_object"
        else:
            match = re.match(r"^(?P<number>\d+)\.\s+(?P<title>.+)$", heading)
            if not match:
                continue
            framework_name = match.group("title").strip()
            framework_id = _normalise_label(framework_name).replace(" ", "_")
            source_kind = "library"
        payload = _parse_key_value_block(lines[1:])
        used_on = tuple(_parse_used_on(payload.get("Used on", ())))
        purpose = " ".join(payload.get("Purpose", ())).strip()
        inputs = _split_csv(" ".join(payload.get("Inputs", ())))
        outputs = _split_csv(" ".join(payload.get("Outputs", ())))
        visual_structure = " ".join(payload.get("Visual structure", ())).strip()
        when_to_use = " ".join(payload.get("When to use", ())).strip()
        structural_rules = tuple(rule for rule in (visual_structure, when_to_use) if rule)
        layout_types = _layout_types_from_used_on(used_on)
        definitions.append(
            VisualFrameworkDefinition(
                framework_id=framework_id,
                framework_name=framework_name,
                source_asset_id=asset.asset_id,
                source_title=asset.source_title,
                source_path=str(asset.path(knowledge_registry.root)),
                source_checksum=asset.checksum,
                source_modified_at=asset.source_modified_at,
                source_kind=source_kind,
                purpose=purpose,
                inputs=inputs,
                outputs=outputs,
                structural_rules=structural_rules,
                visual_type_aliases=(framework_id, _normalise_label(framework_name).replace(" ", "_")),
                used_on=used_on,
                layout_types=layout_types,
                selection_hints=tuple(_extract_framework_hints(framework_name, purpose, inputs, outputs, structural_rules)),
                extensions={
                    "raw_lines": lines,
                    "payload": payload,
                },
            )
        )
    return tuple(definitions)


def _parse_intelligence_rules(
    text: str,
    asset: BlueprintKnowledgeAsset,
    knowledge_registry: BlueprintKnowledgeRegistry,
) -> tuple[tuple[VisualFrameworkDefinition, ...], dict[str, LayoutSpecification], dict[str, Any]]:
    sections = _split_top_level_sections(text)
    copy_limits = _extract_copy_limits(text)
    strategic_sections = _parse_strategy_visual_library(text)
    definitions: list[VisualFrameworkDefinition] = []
    for item in strategic_sections:
        framework_name = item["name"]
        framework_id = _normalise_label(framework_name).replace(" ", "_")
        definitions.append(
            VisualFrameworkDefinition(
                framework_id=framework_id,
                framework_name=framework_name,
                source_asset_id=asset.asset_id,
                source_title=asset.source_title,
                source_path=str(asset.path(knowledge_registry.root)),
                source_checksum=asset.checksum,
                source_modified_at=asset.source_modified_at,
                source_kind="intelligence",
                purpose=item.get("purpose", ""),
                inputs=tuple(item.get("inputs", ())),
                outputs=tuple(item.get("outputs", ())),
                structural_rules=tuple(item.get("structural_rules", ())),
                visual_type_aliases=tuple({framework_id, item.get("alias", framework_id)}),
                used_on=tuple(item.get("used_on", ())),
                layout_types=tuple(item.get("layout_types", ())),
                selection_hints=tuple(item.get("hints", ())),
                extensions=item.get("extensions", {}),
            )
        )

    layout_specs = {
        key: LayoutSpecification(
            layout_type=key,
            layout_name=value["layout_name"],
            summary=value["summary"],
            regions=value["regions"],
            geometry=value["geometry"],
            copy_density_limit_words=copy_limits.get("maximum body copy"),
            paragraph_limit_words=copy_limits.get("maximum paragraph length"),
            bullet_limit=copy_limits.get("maximum bullet count"),
            supported_framework_ids=tuple(value.get("supported_framework_ids", ())),
            extensions={"source_sections": sections},
        )
        for key, value in _layout_catalogue().items()
    }
    return tuple(definitions), layout_specs, _design_tokens_from_text(text)


def _schema_visual_definitions(
    schema,
    asset: BlueprintKnowledgeAsset,
    knowledge_registry: BlueprintKnowledgeRegistry,
) -> tuple[VisualFrameworkDefinition, ...]:
    definitions: list[VisualFrameworkDefinition] = []
    for slide in schema.slides:
        framework_id = _normalise_label(slide.visual_type).replace(" ", "_")
        definitions.append(
            VisualFrameworkDefinition(
                framework_id=framework_id,
                framework_name=slide.slide_name,
                source_asset_id=asset.asset_id,
                source_title=asset.source_title,
                source_path=str(asset.path(knowledge_registry.root)),
                source_checksum=asset.checksum,
                source_modified_at=asset.source_modified_at,
                source_kind="schema",
                purpose=slide.purpose,
                inputs=slide.inputs,
                outputs=slide.outputs,
                structural_rules=(
                    f"slide_no={slide.slide_no}",
                    f"act={slide.act}",
                    f"layout_type={slide.layout_type}",
                    f"so_what_test={slide.so_what_test}",
                ),
                visual_type_aliases=(
                    slide.visual_type,
                    framework_id,
                    _normalise_label(slide.slide_name).replace(" ", "_"),
                ),
                used_on=(f"slide {slide.slide_no}", slide.slide_name),
                layout_types=(slide.layout_type,),
                selection_hints=(slide.purpose, slide.slide_name, slide.visual_type),
                extensions={"schema_slide": slide.to_dict()},
            )
        )
    return tuple(definitions)


def _merge_framework_definitions(first: VisualFrameworkDefinition, second: VisualFrameworkDefinition) -> VisualFrameworkDefinition:
    if first.framework_id != second.framework_id:
        raise ValueError("framework identifiers must match to merge")
    return VisualFrameworkDefinition(
        framework_id=first.framework_id,
        framework_name=first.framework_name,
        source_asset_id=first.source_asset_id,
        source_title=first.source_title,
        source_path=first.source_path,
        source_checksum=first.source_checksum,
        source_modified_at=first.source_modified_at,
        source_kind=first.source_kind,
        purpose=first.purpose or second.purpose,
        inputs=first.inputs + tuple(item for item in second.inputs if item not in first.inputs),
        outputs=first.outputs + tuple(item for item in second.outputs if item not in first.outputs),
        structural_rules=first.structural_rules + tuple(item for item in second.structural_rules if item not in first.structural_rules),
        visual_type_aliases=first.visual_type_aliases + tuple(item for item in second.visual_type_aliases if item not in first.visual_type_aliases),
        used_on=first.used_on + tuple(item for item in second.used_on if item not in first.used_on),
        layout_types=first.layout_types + tuple(item for item in second.layout_types if item not in first.layout_types),
        selection_hints=first.selection_hints + tuple(item for item in second.selection_hints if item not in first.selection_hints),
        extensions={
            **first.extensions,
            **second.extensions,
            "merged_from": [first.to_dict(), second.to_dict()],
        },
    )


def _layout_types_from_used_on(used_on: Sequence[str]) -> tuple[str, ...]:
    layout_types: list[str] = []
    for item in used_on:
        match = re.search(r"\(slide\s*(?P<layout>[A-F])\)", item, re.IGNORECASE)
        if match:
            layout_types.append(match.group("layout").upper())
    return tuple(dict.fromkeys(layout_types))


def _split_on_framework_sections(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    sections: list[list[str]] = []
    current: list[str] = []
    collecting = False
    for line in lines:
        if re.match(r"^\d+\.\s+", line.strip()) or line.strip().startswith(("TITLE LOCKUP", "CONTACT BLOCK")):
            if current:
                sections.append(current)
            current = [line]
            collecting = True
            continue
        if collecting:
            current.append(line)
    if current:
        sections.append(current)
    return tuple("\n".join(section).strip() for section in sections if "\n".join(section).strip())


def _split_top_level_sections(text: str) -> tuple[str, ...]:
    return tuple(section.strip() for section in re.split(r"\n\s*_{8,}\s*\n", text) if section.strip())


def _extract_copy_limits(text: str) -> dict[str, int]:
    limits: dict[str, int] = {}
    for label, pattern in (
        ("maximum body copy", r"Maximum body copy:\s*(\d+)"),
        ("maximum paragraph length", r"Maximum paragraph length:\s*(\d+)"),
        ("maximum bullet count", r"Maximum bullet count:\s*(\d+)"),
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            limits[label] = int(match.group(1))
    return limits


def _parse_strategy_visual_library(text: str) -> tuple[dict[str, Any], ...]:
    strategies: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<index>\d+)\.\s+(?P<name>[A-Z][A-Z /()-]+)\s+Purpose:\s*(?P<purpose>.+?)\s+Structure:\s*(?P<structure>.+?)(?=\n\s*\d+\.\s+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        name = " ".join(word.title() for word in match.group("name").replace("  ", " ").split())
        purpose = " ".join(match.group("purpose").split())
        structure = " ".join(match.group("structure").split())
        strategies.append(
            {
                "name": name,
                "alias": _normalise_label(name).replace(" ", "_"),
                "purpose": purpose,
                "structural_rules": (structure,),
                "inputs": tuple(),
                "outputs": tuple(),
                "used_on": tuple(),
                "layout_types": tuple(),
                "hints": tuple(),
                "extensions": {"raw_text": match.group(0).strip()},
            }
        )
    return tuple(strategies)


def _layout_catalogue() -> dict[str, dict[str, Any]]:
    return {
        "A": {
            "layout_name": "Text and visual split",
            "summary": "Text-left / photo-panel-right split layout.",
            "regions": ("left_text", "right_visual"),
            "geometry": ("text_column", "visual_panel"),
            "supported_framework_ids": (),
        },
        "B": {
            "layout_name": "Full width copy",
            "summary": "Dark full-width copy-led layout.",
            "regions": ("full_bleed_copy",),
            "geometry": ("full_bleed",),
            "supported_framework_ids": (),
        },
        "C": {
            "layout_name": "Two column framework",
            "summary": "Headline and content/diagram split across two columns.",
            "regions": ("lead_column", "support_column"),
            "geometry": ("two_column",),
            "supported_framework_ids": (),
        },
        "D": {
            "layout_name": "Card grid",
            "summary": "Two-to-four card grid for comparisons and territories.",
            "regions": ("card_grid",),
            "geometry": ("grid",),
            "supported_framework_ids": (),
        },
        "E": {
            "layout_name": "Accent pivot",
            "summary": "Full purple accent pivot or section moment.",
            "regions": ("full_accent",),
            "geometry": ("pivot",),
            "supported_framework_ids": (),
        },
        "F": {
            "layout_name": "Strategic scorecard stack",
            "summary": "Full-bleed strategic stack for commercial prize, roadmap and measurement.",
            "regions": ("hero_statement", "support_stack"),
            "geometry": ("full_bleed_stack",),
            "supported_framework_ids": ("commercial_opportunity_model", "constraint_priority_roadmap", "priority_matrix_plus_measurement_stack"),
        },
    }


def _layout_specs(
    intelligence_layouts: Sequence[str],
    schema,
) -> dict[str, LayoutSpecification]:
    catalog = _layout_catalogue()
    schema_support: dict[str, list[str]] = {key: [] for key in catalog}
    for slide in getattr(schema, "slides", ()):
        layout_type = str(getattr(slide, "layout_type", "")).strip().upper()
        if layout_type in schema_support:
            schema_support[layout_type].append(f"{slide.slide_no}:{slide.visual_type}")

    intelligence_lookup: dict[str, dict[str, str]] = {}
    for section in intelligence_layouts:
        label = section.strip()
        if not label:
            continue
        match = re.match(r"^(?P<layout>[A-F])\s+[—=-]\s+(?P<summary>.+)$", label)
        if match:
            intelligence_lookup[match.group("layout").upper()] = {
                "layout_name": match.group("summary").strip(),
                "summary": match.group("summary").strip(),
            }
            continue
        match = re.match(r"^(?P<layout>[A-F])\s*=\s*(?P<summary>.+)$", label)
        if match:
            intelligence_lookup[match.group("layout").upper()] = {
                "layout_name": match.group("summary").strip(),
                "summary": match.group("summary").strip(),
            }

    specs: dict[str, LayoutSpecification] = {}
    for layout_type, value in catalog.items():
        intelligence_value = intelligence_lookup.get(layout_type, {})
        supported_framework_ids = tuple(
            sorted(
                dict.fromkeys(
                    list(value.get("supported_framework_ids", ()))
                    + schema_support.get(layout_type, [])
                )
            )
        )
        specs[layout_type] = LayoutSpecification(
            layout_type=layout_type,
            layout_name=intelligence_value.get("layout_name", value["layout_name"]),
            summary=intelligence_value.get("summary", value["summary"]),
            regions=value["regions"],
            geometry=value["geometry"],
            copy_density_limit_words=100,
            paragraph_limit_words=50,
            bullet_limit=5,
            supported_framework_ids=supported_framework_ids,
            extensions={
                "canonical_support_count": len(supported_framework_ids),
                "source_layout_catalogue": value,
                "intelligence_layout": intelligence_value or None,
            },
        )
    return specs


def _design_tokens_from_text(text: str) -> dict[str, Any]:
    palette = {
        "canvas_primary": "#0D0D1A",
        "canvas_secondary": "#1A1A2E",
        "accent_display": "#A78BFA",
        "accent_section": "#7C3AED",
        "body": "#FFFFFF",
        "labels": "#9CA3AF",
    }
    typography = {
        "font_family": "Arial/Calibri",
        "headline_max_pt": 32,
        "body_max_pt": 14,
        "line_height": 1.4,
    }
    spacing = {
        "sparse_copy": "breathing room",
        "compact_supporting_copy": "balanced hierarchy",
        "pivot_spacing": "section moments",
    }
    hierarchy = {
        "cover": "primary title and accent line",
        "section": "large section signal",
        "body": "supporting explanation",
        "label": "small annotation or source cue",
    }
    line_shape = {
        "axis_line": "used for maps and matrices",
        "card_border": "used for modular evidence",
        "flow_arrow": "used for progression and sequence",
    }
    emphasis = {
        "accent": "lavender",
        "section_accent": "deep purple",
        "body_emphasis": "white text on dark navy",
        "label_emphasis": "grey labels",
    }
    return {
        "palette": palette,
        "typography": typography,
        "spacing": spacing,
        "hierarchy": hierarchy,
        "line_shape": line_shape,
        "emphasis": emphasis,
        "source_checksum": sha256_hex(text),
    }


def _confidence_from_findings(findings: Sequence[RenderValidationFinding]) -> float:
    score = 1.0
    for finding in findings:
        if finding.severity == "info":
            continue
        if finding.severity == "warning":
            score -= 0.03
        elif finding.severity == "error":
            score -= 0.15
        elif finding.severity == "blocking":
            score -= 0.3
    return max(0.0, round(score, 3))
