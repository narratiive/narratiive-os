from __future__ import annotations

import ast
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .artifact_catalog import ArtifactRecord, FileArtifactCatalog
from .execution_package import ExecutionPackage
from .blueprint_knowledge_registry import (
    BlueprintCanonBundle,
    BlueprintCanonBundleComponent,
    BlueprintKnowledgeRegistry,
    BlueprintSchemaSlide,
    BlueprintSchemaV3,
)
from .prompt_registry import FilePromptRegistry, PromptVersion
from .provider import ProviderClient
from .research_engine import sha256_hex, slugify, utc_now


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_ID = "claude-growth-blueprint"
DEFAULT_STAGE_ID = "blueprint_generation"
DEFAULT_AGENT_ID = "blueprint_orchestrator"
DEFAULT_OUTPUT_TYPE = "structured_blueprint"
DEFAULT_RAW_ARTIFACT_TYPE = "blueprint_raw_response"
DEFAULT_STRUCTURED_ARTIFACT_TYPE = "blueprint_structured"


def _safe_identifier(value: str, field_name: str) -> str:
    safe = str(value or "").strip()
    if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
        raise ValueError(f"{field_name} must be a safe identifier")
    return safe


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True, slots=True)
class BlueprintContextArtifacts:
    research_artifacts: tuple[ArtifactRecord, ...] = ()
    strategy_artifacts: tuple[ArtifactRecord, ...] = ()
    campaign_artifacts: tuple[ArtifactRecord, ...] = ()
    creative_artifacts: tuple[ArtifactRecord, ...] = ()
    quality_artifacts: tuple[ArtifactRecord, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        evidence_ids = tuple(dict.fromkeys(str(item).strip() for item in self.evidence_ids if str(item).strip()))
        object.__setattr__(self, "evidence_ids", evidence_ids)

    def all_groups(self) -> tuple[tuple[str, tuple[ArtifactRecord, ...]], ...]:
        return (
            ("research", self.research_artifacts),
            ("strategy", self.strategy_artifacts),
            ("campaign", self.campaign_artifacts),
            ("creative", self.creative_artifacts),
            ("quality", self.quality_artifacts),
        )

    def all_records(self) -> tuple[ArtifactRecord, ...]:
        ordered: list[ArtifactRecord] = []
        seen: set[str] = set()
        for _, records in self.all_groups():
            for record in records:
                artifact_id = record.artifact.artifact_id
                if artifact_id in seen:
                    continue
                seen.add(artifact_id)
                ordered.append(record)
        return tuple(ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_artifacts": [record.to_dict() for record in self.research_artifacts],
            "strategy_artifacts": [record.to_dict() for record in self.strategy_artifacts],
            "campaign_artifacts": [record.to_dict() for record in self.campaign_artifacts],
            "creative_artifacts": [record.to_dict() for record in self.creative_artifacts],
            "quality_artifacts": [record.to_dict() for record in self.quality_artifacts],
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlueprintContextArtifacts":
        return cls(
            research_artifacts=_load_records(data.get("research_artifacts")),
            strategy_artifacts=_load_records(data.get("strategy_artifacts")),
            campaign_artifacts=_load_records(data.get("campaign_artifacts")),
            creative_artifacts=_load_records(data.get("creative_artifacts")),
            quality_artifacts=_load_records(data.get("quality_artifacts")),
            evidence_ids=tuple(str(item).strip() for item in data.get("evidence_ids") or ()),
        )

    def input_artifact_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for record in self.all_records():
            ids.append(record.artifact.artifact_id)
        return tuple(dict.fromkeys(ids))

    def context_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for group, records in self.all_groups():
            for record in records:
                entries.append({"group": group, "artifact_record": record.to_dict()})
        return entries


@dataclass(frozen=True, slots=True)
class BlueprintRequest:
    request_id: str
    workspace_id: str
    client_id: str
    approved_context: BlueprintContextArtifacts = field(default_factory=BlueprintContextArtifacts)
    blueprint_id: str = ""
    approved: bool = False
    draft_mode: bool = False
    requested_by: str = "runtime"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _safe_identifier(self.request_id, "request_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        blueprint_id = str(self.blueprint_id).strip() or self.client_id
        _safe_identifier(blueprint_id, "blueprint_id")
        object.__setattr__(self, "blueprint_id", blueprint_id)
        object.__setattr__(self, "requested_by", str(self.requested_by).strip() or "runtime")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "blueprint_id": self.blueprint_id,
            "approved": self.approved,
            "draft_mode": self.draft_mode,
            "requested_by": self.requested_by,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "approved_context": self.approved_context.to_dict(),
            "request_checksum": self.request_checksum(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlueprintRequest":
        return cls(
            request_id=str(data.get("request_id", "")).strip(),
            workspace_id=str(data.get("workspace_id", "")).strip(),
            client_id=str(data.get("client_id", "")).strip(),
            blueprint_id=str(data.get("blueprint_id", "")).strip(),
            approved_context=BlueprintContextArtifacts.from_dict(
                data.get("approved_context") or {}
            ),
            approved=bool(data.get("approved", False)),
            draft_mode=bool(data.get("draft_mode", False)),
            requested_by=str(data.get("requested_by", "")).strip() or "runtime",
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at", "")).strip() or utc_now(),
        )

    def request_checksum(self) -> str:
        payload = {
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "blueprint_id": self.blueprint_id,
            "approved": self.approved,
            "draft_mode": self.draft_mode,
            "requested_by": self.requested_by,
            "metadata": self.metadata,
            "approved_context": self.approved_context.to_dict(),
        }
        return sha256_hex(_stable_json(payload))


@dataclass(frozen=True, slots=True)
class BlueprintSection:
    heading: str
    level: int
    body: str
    children: tuple["BlueprintSection", ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "heading": self.heading,
            "level": self.level,
            "body": self.body,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True, slots=True)
class BlueprintValidationFinding:
    code: str
    severity: str
    message: str
    location: str = ""
    evidence_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.code, "code")
        severity = str(self.severity).strip().lower()
        if severity not in {"info", "warning", "error", "blocking"}:
            raise ValueError("severity must be info, warning, error, or blocking")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(dict.fromkeys(str(item).strip() for item in self.evidence_ids if str(item).strip())),
        )
        object.__setattr__(
            self,
            "artifact_ids",
            tuple(dict.fromkeys(str(item).strip() for item in self.artifact_ids if str(item).strip())),
        )
        object.__setattr__(self, "details", dict(self.details or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "evidence_ids": list(self.evidence_ids),
            "artifact_ids": list(self.artifact_ids),
            "details": dict(self.details),
        }

    @property
    def is_blocking(self) -> bool:
        return self.severity == "blocking"


ValidationFinding = BlueprintValidationFinding


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    source_note: str = ""
    slide_no: int | None = None
    slide_name: str = ""
    claim: str = ""
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.evidence_id, "evidence_id")
        object.__setattr__(self, "source_note", str(self.source_note).strip())
        object.__setattr__(self, "slide_name", str(self.slide_name).strip())
        object.__setattr__(self, "claim", str(self.claim).strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_note": self.source_note,
            "slide_no": self.slide_no,
            "slide_name": self.slide_name,
            "claim": self.claim,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class SourceNote:
    text: str
    evidence_ids: tuple[str, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", str(self.text).strip())
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(dict.fromkeys(str(item).strip() for item in self.evidence_ids if str(item).strip())),
        )
        object.__setattr__(
            self,
            "evidence_references",
            tuple(self.evidence_references),
        )
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class SlideContent:
    thesis: tuple[str, ...] = ()
    founder_insight: tuple[str, ...] = ()
    so_what: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    visual_direction: tuple[str, ...] = ()
    speaker_notes: tuple[str, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "thesis",
            tuple(dict.fromkeys(str(item).strip() for item in self.thesis if str(item).strip())),
        )
        object.__setattr__(
            self,
            "founder_insight",
            tuple(dict.fromkeys(str(item).strip() for item in self.founder_insight if str(item).strip())),
        )
        object.__setattr__(
            self,
            "so_what",
            tuple(dict.fromkeys(str(item).strip() for item in self.so_what if str(item).strip())),
        )
        object.__setattr__(
            self,
            "source_notes",
            tuple(self.source_notes),
        )
        object.__setattr__(
            self,
            "visual_direction",
            tuple(dict.fromkeys(str(item).strip() for item in self.visual_direction if str(item).strip())),
        )
        object.__setattr__(
            self,
            "speaker_notes",
            tuple(dict.fromkeys(str(item).strip() for item in self.speaker_notes if str(item).strip())),
        )
        object.__setattr__(
            self,
            "evidence_references",
            tuple(self.evidence_references),
        )
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "thesis": list(self.thesis),
            "founder_insight": list(self.founder_insight),
            "so_what": list(self.so_what),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "visual_direction": list(self.visual_direction),
            "speaker_notes": list(self.speaker_notes),
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
            "extensions": dict(self.extensions),
        }

    def to_legacy_sections(self) -> tuple["BlueprintSection", ...]:
        sections: list[BlueprintSection] = []
        if self.thesis:
            sections.append(BlueprintSection("Thesis", 4, "\n".join(self.thesis), ()))
        if self.founder_insight:
            sections.append(BlueprintSection("Founder Insight", 4, "\n".join(self.founder_insight), ()))
        if self.so_what:
            sections.append(BlueprintSection("So What", 4, "\n".join(self.so_what), ()))
        if self.source_notes:
            sections.append(
                BlueprintSection(
                    "Source Notes",
                    4,
                    "\n".join(
                        f"- {note.text}" if not note.text.startswith("-") else note.text
                        for note in self.source_notes
                    ),
                    (),
                )
            )
        if self.visual_direction:
            sections.append(
                BlueprintSection("Visual / Layout Direction", 4, "\n".join(self.visual_direction), ())
            )
        if self.speaker_notes:
            sections.append(BlueprintSection("Speaker Notes", 4, "\n".join(self.speaker_notes), ()))
        for heading, value in self.extensions.items():
            sections.append(_extension_to_section(heading, value))
        return tuple(sections)


@dataclass(frozen=True, slots=True)
class BlueprintSlide:
    slide_no: int
    slide_name: str
    act: str
    purpose: str
    visual_type: str
    layout_type: str
    content_requirements: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    so_what_test: str
    content: SlideContent = field(default_factory=SlideContent)
    confidence: float = 1.0
    validation_findings: tuple[BlueprintValidationFinding, ...] = ()
    source_slide_name: str = ""
    source_act_name: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.slide_no <= 0:
            raise ValueError("slide_no must be positive")
        object.__setattr__(self, "slide_name", str(self.slide_name).strip())
        object.__setattr__(self, "act", str(self.act).strip())
        object.__setattr__(self, "purpose", str(self.purpose).strip())
        object.__setattr__(self, "visual_type", str(self.visual_type).strip())
        object.__setattr__(self, "layout_type", str(self.layout_type).strip())
        object.__setattr__(
            self,
            "content_requirements",
            tuple(dict.fromkeys(str(item).strip() for item in self.content_requirements if str(item).strip())),
        )
        object.__setattr__(
            self,
            "inputs",
            tuple(dict.fromkeys(str(item).strip() for item in self.inputs if str(item).strip())),
        )
        object.__setattr__(
            self,
            "outputs",
            tuple(dict.fromkeys(str(item).strip() for item in self.outputs if str(item).strip())),
        )
        object.__setattr__(self, "so_what_test", str(self.so_what_test).strip())
        object.__setattr__(self, "content", self.content)
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "source_slide_name", str(self.source_slide_name).strip())
        object.__setattr__(self, "source_act_name", str(self.source_act_name).strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    @property
    def heading(self) -> str:
        return f"Slide {self.slide_no} — {self.slide_name}"

    @property
    def children(self) -> tuple[BlueprintSection, ...]:
        return self.content.to_legacy_sections()

    @property
    def founder_insight(self) -> tuple[str, ...]:
        return self.content.founder_insight

    @property
    def so_what(self) -> tuple[str, ...]:
        return self.content.so_what

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_no": self.slide_no,
            "slide_name": self.slide_name,
            "act": self.act,
            "purpose": self.purpose,
            "visual_type": self.visual_type,
            "layout_type": self.layout_type,
            "content_requirements": list(self.content_requirements),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "so_what_test": self.so_what_test,
            "content": self.content.to_dict(),
            "confidence": self.confidence,
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "source_slide_name": self.source_slide_name,
            "source_act_name": self.source_act_name,
            "extensions": dict(self.extensions),
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "heading": self.source_slide_name or self.heading,
            "level": 3,
            "body": "",
            "children": [section.to_dict() for section in self.children],
        }


@dataclass(frozen=True, slots=True)
class BlueprintAct:
    act_no: int
    act_name: str
    slides: tuple[BlueprintSlide, ...]
    confidence: float = 1.0
    validation_findings: tuple[BlueprintValidationFinding, ...] = ()
    source_act_name: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.act_no <= 0:
            raise ValueError("act_no must be positive")
        object.__setattr__(self, "act_name", str(self.act_name).strip())
        object.__setattr__(self, "slides", tuple(self.slides))
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "source_act_name", str(self.source_act_name).strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    @property
    def heading(self) -> str:
        return self.act_name

    @property
    def children(self) -> tuple[BlueprintSlide, ...]:
        return self.slides

    def to_dict(self) -> dict[str, Any]:
        return {
            "act_no": self.act_no,
            "act_name": self.act_name,
            "slides": [slide.to_dict() for slide in self.slides],
            "confidence": self.confidence,
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "source_act_name": self.source_act_name,
            "extensions": dict(self.extensions),
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "heading": self.source_act_name or self.heading,
            "level": 2,
            "body": "",
            "children": [slide.to_legacy_dict() for slide in self.slides],
        }


@dataclass(frozen=True, slots=True)
class BlueprintLineage:
    canon_bundle: BlueprintCanonBundle
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    provider_id: str
    model_id: str
    requested_provider_id: str
    requested_model_id: str
    routing_policy_id: str
    routing_policy_version: str
    evidence_pack_ids: tuple[str, ...]
    raw_response_artifact: ArtifactRecord
    structured_artifact: ArtifactRecord | None = None
    artifact_lineage: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt_id", str(self.prompt_id).strip())
        object.__setattr__(self, "prompt_version", int(self.prompt_version))
        object.__setattr__(self, "prompt_checksum", str(self.prompt_checksum).strip())
        object.__setattr__(self, "provider_id", str(self.provider_id).strip())
        object.__setattr__(self, "model_id", str(self.model_id).strip())
        object.__setattr__(self, "requested_provider_id", str(self.requested_provider_id).strip())
        object.__setattr__(self, "requested_model_id", str(self.requested_model_id).strip())
        object.__setattr__(self, "routing_policy_id", str(self.routing_policy_id).strip())
        object.__setattr__(self, "routing_policy_version", str(self.routing_policy_version).strip())
        object.__setattr__(
            self,
            "evidence_pack_ids",
            tuple(dict.fromkeys(str(item).strip() for item in self.evidence_pack_ids if str(item).strip())),
        )
        object.__setattr__(self, "artifact_lineage", tuple(dict.fromkeys(self.artifact_lineage)))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        data = {
            "canon_bundle": self.canon_bundle.to_dict(),
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "requested_provider_id": self.requested_provider_id,
            "requested_model_id": self.requested_model_id,
            "routing_policy_id": self.routing_policy_id,
            "routing_policy_version": self.routing_policy_version,
            "evidence_pack_ids": list(self.evidence_pack_ids),
            "raw_response_artifact": self.raw_response_artifact.to_dict(),
            "artifact_lineage": list(self.artifact_lineage),
            "extensions": dict(self.extensions),
        }
        if self.structured_artifact is not None:
            data["structured_artifact"] = self.structured_artifact.to_dict()
        return data


@dataclass(frozen=True, slots=True)
class BlueprintChangeSummary:
    field: str
    before: Any
    after: Any
    reason: str = ""

    def __post_init__(self) -> None:
        _safe_identifier(self.field, "field")

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class StructuredBlueprint:
    blueprint_id: str
    blueprint_version: int
    request_id: str
    workspace_id: str
    client_id: str
    document_title: str
    raw_response: str
    acts: tuple[BlueprintAct, ...]
    lineage: BlueprintLineage
    validation_findings: tuple[BlueprintValidationFinding, ...]
    outline_hash: str
    evidence_ids: tuple[str, ...]
    status: str
    confidence: float = 1.0
    created_at: str = field(default_factory=utc_now)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.blueprint_id, "blueprint_id")
        if self.blueprint_version <= 0:
            raise ValueError("blueprint_version must be positive")
        _safe_identifier(self.request_id, "request_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        object.__setattr__(self, "document_title", str(self.document_title).strip())
        status = str(self.status).strip().lower()
        object.__setattr__(self, "status", status or "complete")
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(dict.fromkeys(str(item).strip() for item in self.evidence_ids if str(item).strip())),
        )
        object.__setattr__(self, "acts", tuple(self.acts))
        object.__setattr__(self, "lineage", self.lineage)
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    @property
    def sections(self) -> tuple[BlueprintAct, ...]:
        return self.acts

    @property
    def slides(self) -> tuple[BlueprintSlide, ...]:
        return tuple(slide for act in self.acts for slide in act.slides)

    @property
    def canon_bundle(self) -> BlueprintCanonBundle:
        return self.lineage.canon_bundle

    @property
    def prompt_id(self) -> str:
        return self.lineage.prompt_id

    @property
    def prompt_version(self) -> int:
        return self.lineage.prompt_version

    @property
    def prompt_checksum(self) -> str:
        return self.lineage.prompt_checksum

    @property
    def provider_id(self) -> str:
        return self.lineage.provider_id

    @property
    def model_id(self) -> str:
        return self.lineage.model_id

    @property
    def requested_provider_id(self) -> str:
        return self.lineage.requested_provider_id

    @property
    def requested_model_id(self) -> str:
        return self.lineage.requested_model_id

    @property
    def routing_policy_id(self) -> str:
        return self.lineage.routing_policy_id

    @property
    def routing_policy_version(self) -> str:
        return self.lineage.routing_policy_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "document_title": self.document_title,
            "raw_response": self.raw_response,
            "acts": [act.to_dict() for act in self.acts],
            "sections": [act.to_legacy_dict() for act in self.acts],
            "slides": [slide.to_dict() for slide in self.slides],
            "lineage": self.lineage.to_dict(),
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "outline_hash": self.outline_hash,
            "evidence_ids": list(self.evidence_ids),
            "status": self.status,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StructuredBlueprint":
        acts_data = data.get("acts")
        if acts_data is None:
            acts_data = data.get("sections") or []
        acts = _load_acts(acts_data)
        lineage_data = data.get("lineage") or {}
        lineage = _load_lineage(lineage_data)
        return cls(
            blueprint_id=str(data["blueprint_id"]),
            blueprint_version=int(data.get("blueprint_version", data.get("version", 1))),
            request_id=str(data["request_id"]),
            workspace_id=str(data["workspace_id"]),
            client_id=str(data["client_id"]),
            document_title=str(data.get("document_title", "")),
            raw_response=str(data["raw_response"]),
            acts=acts,
            lineage=lineage,
            validation_findings=_load_findings(data.get("validation_findings") or []),
            outline_hash=str(data["outline_hash"]),
            evidence_ids=tuple(data.get("evidence_ids") or ()),
            status=str(data.get("status", "complete")),
            confidence=float(data.get("confidence", 1.0)),
            created_at=str(data.get("created_at", utc_now())),
            extensions=dict(data.get("extensions") or {}),
        )


@dataclass(frozen=True, slots=True)
class BlueprintEngineResponse:
    raw_response: str
    provider_id: str
    model_id: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    requested_provider_id: str = ""
    requested_model_id: str = ""
    routing_policy_id: str = ""
    routing_policy_version: str = ""
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.provider_id, "provider_id")
        _safe_identifier(self.model_id, "model_id")
        _safe_identifier(self.prompt_id, "prompt_id")
        if self.requested_provider_id:
            _safe_identifier(self.requested_provider_id, "requested_provider_id")
        if self.requested_model_id:
            _safe_identifier(self.requested_model_id, "requested_model_id")
        if self.routing_policy_id:
            _safe_identifier(self.routing_policy_id, "routing_policy_id")
        if self.routing_policy_version:
            _safe_identifier(self.routing_policy_version, "routing_policy_version")
        object.__setattr__(self, "provider_metadata", dict(self.provider_metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_response": self.raw_response,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
            "requested_provider_id": self.requested_provider_id,
            "requested_model_id": self.requested_model_id,
            "routing_policy_id": self.routing_policy_id,
            "routing_policy_version": self.routing_policy_version,
            "provider_metadata": dict(self.provider_metadata),
        }


@dataclass(frozen=True, slots=True)
class BlueprintVersionRecord:
    blueprint_id: str
    workspace_id: str
    client_id: str
    version: int
    request: BlueprintRequest
    input_checksum: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    provider_id: str
    model_id: str
    requested_provider_id: str
    requested_model_id: str
    routing_policy_id: str
    routing_policy_version: str
    canon_bundle: BlueprintCanonBundle
    structured_blueprint: StructuredBlueprint
    raw_response_artifact: ArtifactRecord
    structured_artifact: ArtifactRecord
    validation_findings: tuple[BlueprintValidationFinding, ...]
    change_summary: tuple[BlueprintChangeSummary, ...]
    previous_version: int | None
    artifact_lineage: tuple[str, ...]
    status: str
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _safe_identifier(self.blueprint_id, "blueprint_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        if self.version <= 0:
            raise ValueError("version must be positive")
        object.__setattr__(self, "artifact_lineage", tuple(dict.fromkeys(self.artifact_lineage)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "version": self.version,
            "request": self.request.to_dict(),
            "input_checksum": self.input_checksum,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "requested_provider_id": self.requested_provider_id,
            "requested_model_id": self.requested_model_id,
            "routing_policy_id": self.routing_policy_id,
            "routing_policy_version": self.routing_policy_version,
            "canon_bundle": self.canon_bundle.to_dict(),
            "structured_blueprint": self.structured_blueprint.to_dict(),
            "raw_response_artifact": self.raw_response_artifact.to_dict(),
            "structured_artifact": self.structured_artifact.to_dict(),
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "change_summary": [summary.to_dict() for summary in self.change_summary],
            "previous_version": self.previous_version,
            "artifact_lineage": list(self.artifact_lineage),
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BlueprintVersionRecord":
        structured_blueprint = StructuredBlueprint.from_dict(data.get("structured_blueprint") or {})
        request = BlueprintRequest.from_dict(data["request"])
        return cls(
            blueprint_id=str(data["blueprint_id"]),
            workspace_id=str(data["workspace_id"]),
            client_id=str(data["client_id"]),
            version=int(data["version"]),
            request=request,
            input_checksum=str(data["input_checksum"]),
            prompt_id=str(data["prompt_id"]),
            prompt_version=int(data["prompt_version"]),
            prompt_checksum=str(data["prompt_checksum"]),
            provider_id=str(data["provider_id"]),
            model_id=str(data["model_id"]),
            requested_provider_id=str(data.get("requested_provider_id", data["provider_id"])),
            requested_model_id=str(data.get("requested_model_id", data["model_id"])),
            routing_policy_id=str(data.get("routing_policy_id", "")),
            routing_policy_version=str(data.get("routing_policy_version", "")),
            canon_bundle=structured_blueprint.canon_bundle,
            structured_blueprint=structured_blueprint,
            raw_response_artifact=ArtifactRecord.from_dict(data["raw_response_artifact"]),
            structured_artifact=ArtifactRecord.from_dict(data["structured_artifact"]),
            validation_findings=_load_findings(data.get("validation_findings") or []),
            change_summary=tuple(
                BlueprintChangeSummary(
                    field=str(item["field"]),
                    before=item.get("before"),
                    after=item.get("after"),
                    reason=str(item.get("reason", "")),
                )
                for item in data.get("change_summary") or []
            ),
            previous_version=(
                int(data["previous_version"])
                if data.get("previous_version") is not None
                else None
            ),
            artifact_lineage=tuple(data.get("artifact_lineage") or ()),
            status=str(data.get("status", "complete")),
            created_at=str(data.get("created_at", utc_now())),
        )


@runtime_checkable
class BlueprintEngine(Protocol):
    name: str

    def generate(self, request: BlueprintRequest, prompt: PromptVersion) -> BlueprintEngineResponse:
        ...


class FakeBlueprintEngine:
    name = "fake_blueprint_engine"

    def __init__(
        self,
        raw_response: str,
        *,
        provider_id: str = "fake-provider",
        model_id: str = "fake-model",
    ) -> None:
        self.raw_response = raw_response
        self.provider_id = provider_id
        self.model_id = model_id

    def generate(self, request: BlueprintRequest, prompt: PromptVersion) -> BlueprintEngineResponse:
        return BlueprintEngineResponse(
            raw_response=self.raw_response,
            provider_id=self.provider_id,
            model_id=self.model_id,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            requested_provider_id=self.provider_id,
            requested_model_id=self.model_id,
            routing_policy_id="static",
            routing_policy_version="1",
            provider_metadata={
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "engine": self.name,
            },
        )


class ClaudeBlueprintEngine:
    name = "claude_blueprint_engine"

    def __init__(
        self,
        provider: ProviderClient,
        *,
        prompt_registry: FilePromptRegistry,
        prompt_source_path: str | Path | None = None,
        prompt_id: str = DEFAULT_PROMPT_ID,
        stage_id: str = DEFAULT_STAGE_ID,
        agent_id: str = DEFAULT_AGENT_ID,
        routing_policy_id: str = "claude_only",
        routing_policy_version: str = "1",
        expected_provider_id: str = "anthropic",
        expected_model_id: str = "claude-sonnet-4-5",
    ) -> None:
        self.provider = provider
        self.prompt_registry = prompt_registry
        self.prompt_source_path = Path(prompt_source_path) if prompt_source_path is not None else None
        self.prompt_id = prompt_id
        self.stage_id = stage_id
        self.agent_id = agent_id
        self.routing_policy_id = routing_policy_id
        self.routing_policy_version = routing_policy_version
        self.expected_provider_id = expected_provider_id
        self.expected_model_id = expected_model_id

    def generate(self, request: BlueprintRequest, prompt: PromptVersion) -> BlueprintEngineResponse:
        prompt_source_path = self.prompt_source_path or Path(str(prompt.metadata.get("source_path") or ""))
        package = ExecutionPackage(
            schema_version=1,
            job_id=request.request_id,
            run_id=request.blueprint_id,
            stage_id=self.stage_id,
            agent_id=self.agent_id,
            agent_version=str(prompt.version),
            agent_ref=str(prompt_source_path),
            instructions=prompt.content,
            input_artifacts=tuple(
                {
                    "artifact_id": record.artifact.artifact_id,
                    "artifact_type": record.artifact.artifact_type,
                    "location": record.artifact.location,
                    "checksum": record.artifact.checksum,
                    "metadata": dict(record.artifact.metadata),
                }
                for record in request.approved_context.all_records()
            ),
            memory_records=(),
            confidence_scorecard=None,
            context=self._context(request, prompt),
            expected_output_type=DEFAULT_OUTPUT_TYPE,
        )
        response = self.provider.generate(package)
        response_metadata = dict(response.metadata or {})
        routing_metadata = response_metadata.get("routing")
        if routing_metadata is not None and not isinstance(routing_metadata, Mapping):
            raise BlueprintRoutingMismatchError(
                "blueprint routing metadata must be an object when provided"
            )
        requested_provider_id = self.expected_provider_id
        requested_model_id = self.expected_model_id
        requested_routing_policy_id = self.routing_policy_id
        requested_routing_policy_version = self.routing_policy_version
        if isinstance(routing_metadata, Mapping):
            requested_provider_id = str(
                routing_metadata.get("provider_id") or requested_provider_id
            ).strip()
            requested_model_id = str(
                routing_metadata.get("model_id") or requested_model_id
            ).strip()
            requested_routing_policy_id = str(
                routing_metadata.get("policy_id") or requested_routing_policy_id
            ).strip()
            requested_routing_policy_version = str(
                routing_metadata.get("policy_version") or requested_routing_policy_version
            ).strip()
        provider_id = str(response_metadata.get("provider_id", "")).strip()
        model_id = str(response_metadata.get("model_id", "")).strip()
        if not provider_id or not model_id:
            raise BlueprintRoutingMismatchError(
                "blueprint provider response did not include provider/model metadata"
            )
        if (
            requested_routing_policy_id == "claude_only"
            and (
                provider_id != self.expected_provider_id
                or model_id != self.expected_model_id
            )
        ):
            raise BlueprintRoutingMismatchError(
                "blueprint routing policy resolved to "
                f"{provider_id}/{model_id} but Claude-only execution requires "
                f"{self.expected_provider_id}/{self.expected_model_id}"
            )
        return BlueprintEngineResponse(
            raw_response=response.content,
            provider_id=provider_id,
            model_id=model_id,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            requested_provider_id=requested_provider_id,
            requested_model_id=requested_model_id,
            routing_policy_id=requested_routing_policy_id,
            routing_policy_version=requested_routing_policy_version,
            provider_metadata=response_metadata,
        )

    def _context(self, request: BlueprintRequest, prompt: PromptVersion) -> dict[str, Any]:
        return {
            "request": {
                "request_id": request.request_id,
                "workspace_id": request.workspace_id,
                "client_id": request.client_id,
                "blueprint_id": request.blueprint_id,
                "approved": request.approved,
                "draft_mode": request.draft_mode,
                "requested_by": request.requested_by,
                "created_at": request.created_at,
                "metadata": dict(request.metadata),
                "request_checksum": request.request_checksum(),
            },
            "approved_context": request.approved_context.to_dict(),
            "prompt": {
                "prompt_id": prompt.prompt_id,
                "version": prompt.version,
                "checksum": prompt.checksum,
                "source_path": str(self.prompt_source_path or prompt.metadata.get("source_path", "")),
            },
            "engine": {
                "name": self.name,
                "expected_provider_id": self.expected_provider_id,
                "expected_model_id": self.expected_model_id,
            },
        }


class BlueprintBlockedError(RuntimeError):
    pass


class BlueprintRoutingMismatchError(BlueprintBlockedError):
    pass


class FileBlueprintStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _directory(self, workspace_id: str, client_id: str, blueprint_id: str) -> Path:
        return (
            self.root
            / "workspaces"
            / slugify(workspace_id)
            / "clients"
            / slugify(client_id)
            / slugify(blueprint_id)
            / "versions"
        )

    def history(self, workspace_id: str, client_id: str, blueprint_id: str) -> list[BlueprintVersionRecord]:
        directory = self._directory(workspace_id, client_id, blueprint_id)
        if not directory.exists():
            return []
        records: list[BlueprintVersionRecord] = []
        for path in sorted(directory.glob("v*.json")):
            records.append(BlueprintVersionRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return sorted(records, key=lambda item: item.version)

    def latest(self, workspace_id: str, client_id: str, blueprint_id: str) -> BlueprintVersionRecord | None:
        history = self.history(workspace_id, client_id, blueprint_id)
        return history[-1] if history else None

    def get(
        self,
        workspace_id: str,
        client_id: str,
        blueprint_id: str,
        version: int,
    ) -> BlueprintVersionRecord:
        directory = self._directory(workspace_id, client_id, blueprint_id)
        path = directory / f"v{version}.json"
        if not path.exists():
            raise KeyError(
                f"blueprint version not found: {workspace_id}/{client_id}/{blueprint_id}@{version}"
            )
        return BlueprintVersionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, record: BlueprintVersionRecord) -> Path:
        directory = self._directory(record.workspace_id, record.client_id, record.blueprint_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"v{record.version}.json"
        if path.exists():
            raise ValueError(f"blueprint version already exists: {path.name}")
        _atomic_write_text(path, json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n")
        return path


class BlueprintOrchestrator:
    def __init__(
        self,
        *,
        artifact_catalog: FileArtifactCatalog,
        prompt_registry: FilePromptRegistry,
        engine: BlueprintEngine,
        knowledge_registry: BlueprintKnowledgeRegistry | None = None,
        store: FileBlueprintStore | None = None,
        prompt_id: str = DEFAULT_PROMPT_ID,
    ) -> None:
        self.artifact_catalog = artifact_catalog
        self.prompt_registry = prompt_registry
        self.engine = engine
        self.knowledge_registry = knowledge_registry or BlueprintKnowledgeRegistry.from_default()
        self.store = store or FileBlueprintStore(Path(self.artifact_catalog.root).parent / "blueprints")
        self.prompt_id = prompt_id

    def for_runtime(self, runtime: Any) -> "BlueprintOrchestrator":
        return BlueprintOrchestrator(
            artifact_catalog=runtime.artifact_catalog,
            prompt_registry=runtime.prompt_registry,
            engine=self.engine,
            knowledge_registry=self.knowledge_registry,
            store=FileBlueprintStore(Path(runtime.artifact_catalog.root).parent / "blueprints"),
            prompt_id=self.prompt_id,
        )

    def generate(self, request: BlueprintRequest) -> BlueprintVersionRecord:
        self._validate_request(request)
        bundle = self.knowledge_registry.active_bundle()
        prompt = self._load_prompt_version()
        response = self.engine.generate(request, prompt)
        previous = self.store.latest(request.workspace_id, request.client_id, request.blueprint_id)
        version = previous.version + 1 if previous else 1
        raw_artifact = self.artifact_catalog.register(
            run_id=request.blueprint_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_RAW_ARTIFACT_TYPE,
            content=response.raw_response,
            parent_artifact_ids=request.approved_context.input_artifact_ids(),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata={
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.version,
                "prompt_checksum": prompt.checksum,
                "provider_id": response.provider_id,
                "model_id": response.model_id,
                "requested_provider_id": response.requested_provider_id,
                "requested_model_id": response.requested_model_id,
                "routing_policy_id": response.routing_policy_id,
                "routing_policy_version": response.routing_policy_version,
                "canon_bundle": bundle.to_dict(),
                "request_id": request.request_id,
            },
        )
        structured_blueprint, findings = self._structure_response(
            request,
            response,
            raw_artifact,
            prompt=prompt,
            bundle=bundle,
            blueprint_version=version,
        )
        structured_artifact = self.artifact_catalog.register(
            run_id=request.blueprint_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_STRUCTURED_ARTIFACT_TYPE,
            content=_stable_json(structured_blueprint.to_dict()),
            parent_artifact_ids=(raw_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata={
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.version,
                "prompt_checksum": prompt.checksum,
                "provider_id": response.provider_id,
                "model_id": response.model_id,
                "requested_provider_id": response.requested_provider_id,
                "requested_model_id": response.requested_model_id,
                "routing_policy_id": response.routing_policy_id,
                "routing_policy_version": response.routing_policy_version,
                "canon_bundle": bundle.to_dict(),
                "request_id": request.request_id,
            },
        )
        change_summary = self._summarise_changes(
            previous,
            request,
            bundle,
            prompt,
            response,
            structured_blueprint,
            raw_artifact,
            structured_artifact,
        )
        record = BlueprintVersionRecord(
            blueprint_id=request.blueprint_id,
            workspace_id=request.workspace_id,
            client_id=request.client_id,
            version=version,
            request=request,
            input_checksum=request.request_checksum(),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            provider_id=response.provider_id,
            model_id=response.model_id,
            requested_provider_id=response.requested_provider_id,
            requested_model_id=response.requested_model_id,
            routing_policy_id=response.routing_policy_id,
            routing_policy_version=response.routing_policy_version,
            canon_bundle=bundle,
            structured_blueprint=structured_blueprint,
            raw_response_artifact=raw_artifact,
            structured_artifact=structured_artifact,
            validation_findings=structured_blueprint.validation_findings,
            change_summary=change_summary,
            previous_version=previous.version if previous else None,
            artifact_lineage=self._artifact_lineage(request, raw_artifact, structured_artifact),
            status=structured_blueprint.status,
        )
        self.store.save(record)
        return record

    def get(
        self,
        workspace_id: str,
        client_id: str,
        blueprint_id: str,
        version: int | None = None,
    ) -> BlueprintVersionRecord:
        if version is None:
            latest = self.store.latest(workspace_id, client_id, blueprint_id)
            if latest is None:
                raise KeyError(f"blueprint not found: {workspace_id}/{client_id}/{blueprint_id}")
            return latest
        return self.store.get(workspace_id, client_id, blueprint_id, version)

    def list(self, workspace_id: str, client_id: str, blueprint_id: str) -> list[BlueprintVersionRecord]:
        return self.store.history(workspace_id, client_id, blueprint_id)

    def _validate_request(self, request: BlueprintRequest) -> None:
        if not request.approved and not request.draft_mode:
            raise BlueprintBlockedError("Blueprint request is not approved.")
        if not request.approved_context.all_records() and not request.draft_mode:
            raise BlueprintBlockedError("Blueprint request has no approved context.")
        for record in request.approved_context.all_records():
            if record.workspace_id != request.workspace_id:
                raise BlueprintBlockedError(
                    f"artifact {record.artifact.artifact_id} belongs to workspace {record.workspace_id}, "
                    f"not {request.workspace_id}"
                )

    def _load_prompt_version(self) -> PromptVersion:
        bundle = self.knowledge_registry.active_bundle()
        prompt_asset = self.knowledge_registry.prompt_asset(bundle)
        if not prompt_asset.path(self.knowledge_registry.root).is_file():
            raise BlueprintBlockedError(
                f"Blueprint prompt source not found: {prompt_asset.path(self.knowledge_registry.root)}"
            )
        content = prompt_asset.read_text(self.knowledge_registry.root)
        metadata = self._prompt_metadata(prompt_asset, bundle)
        history = self.prompt_registry.history(self.prompt_id)
        if history and history[-1].content == content and history[-1].metadata == metadata:
            prompt = history[-1]
        else:
            prompt = self.prompt_registry.publish(
                self.prompt_id,
                content,
                metadata=metadata,
            )
        self.prompt_registry.activate(self.prompt_id, prompt.version)
        return prompt

    def _prompt_metadata(self, prompt_asset: Any, bundle: BlueprintCanonBundle) -> dict[str, Any]:
        supporting_sources = [
            {
                **asset.to_dict(),
                "source_path": str(asset.path(self.knowledge_registry.root)),
                "source_checksum": asset.checksum,
            }
            for asset in self.knowledge_registry.supporting_assets(bundle)
        ]
        return {
            "source_path": str(prompt_asset.path(self.knowledge_registry.root)),
            "source_title": prompt_asset.source_title,
            "source_document_id": prompt_asset.drive_document_id,
            "source_url": prompt_asset.drive_url,
            "source_modified_at": prompt_asset.source_modified_at,
            "source_checksum": prompt_asset.checksum,
            "purpose": "claude_blueprint_orchestration",
            # Keep the historical metadata aliases so older prompt consumers can
            # read the same canonical bundle and source asset details without
            # losing the newer canon_bundle/source_* fields.
            "prompt_asset": {
                **prompt_asset.to_dict(),
                "source_path": str(prompt_asset.path(self.knowledge_registry.root)),
                "source_checksum": prompt_asset.checksum,
            },
            "bundle": bundle.to_dict(),
            "canon_bundle": bundle.to_dict(),
            "supporting_instruction_sources": supporting_sources,
        }

    def _structure_response(
        self,
        request: BlueprintRequest,
        response: BlueprintEngineResponse,
        raw_artifact: ArtifactRecord,
        *,
        prompt: PromptVersion,
        bundle: BlueprintCanonBundle,
        blueprint_version: int,
    ) -> tuple[StructuredBlueprint, tuple[BlueprintValidationFinding, ...]]:
        schema = self.knowledge_registry.schema()
        sections = _parse_markdown_sections(response.raw_response)
        document_title, response_roots = _unpack_response_sections(sections)
        evidence_ids = tuple(dict.fromkeys(_evidence_ids(response.raw_response)))
        findings: list[BlueprintValidationFinding] = []
        if not response.raw_response.strip():
            findings.append(
                BlueprintValidationFinding(
                    code="missing_output",
                    severity="error",
                    message="Blueprint engine returned an empty response.",
                    location="raw_response",
                )
            )
        if not response_roots:
            findings.append(
                BlueprintValidationFinding(
                    code="missing_outline",
                    severity="error",
                    message="Blueprint response did not contain any markdown sections.",
                    location="raw_response",
                )
            )
        raw_candidates = _collect_slide_candidates(response_roots)
        raw_act_count = len([section for section in response_roots if _is_act_heading(section.heading)])
        legacy_mode = raw_act_count < len(schema.acts)
        canonical_acts, alignment_findings = _canonicalise_blueprint_response(
            schema=schema,
            roots=response_roots,
            raw_candidates=raw_candidates,
            evidence_ids=evidence_ids,
            request=request,
            legacy_mode=legacy_mode,
        )
        findings.extend(alignment_findings)
        missing_evidence = [item for item in request.approved_context.evidence_ids if item not in evidence_ids]
        if missing_evidence:
            findings.append(
                BlueprintValidationFinding(
                    code="missing_evidence_references",
                    severity="error",
                    message="Material claims must reference evidence IDs.",
                    location="raw_response",
                    evidence_ids=tuple(missing_evidence),
                    details={"missing_evidence_ids": missing_evidence},
                )
            )
        outline_hash = sha256_hex(
            _stable_json(
                [
                    {
                        "document_title": document_title,
                        "heading": section.heading,
                        "level": section.level,
                        "body_hash": sha256_hex(section.body),
                        "children": [
                            {
                                "heading": child.heading,
                                "level": child.level,
                                "body_hash": sha256_hex(child.body),
                            }
                            for child in section.children
                        ],
                    }
                    for section in response_roots
                ]
            )
        )
        status = self._status(request, findings)
        confidence = _confidence_from_findings(tuple(findings))
        structured = StructuredBlueprint(
            blueprint_id=request.blueprint_id,
            blueprint_version=blueprint_version,
            request_id=request.request_id,
            workspace_id=request.workspace_id,
            client_id=request.client_id,
            document_title=document_title,
            raw_response=response.raw_response,
            acts=canonical_acts,
            lineage=BlueprintLineage(
                canon_bundle=bundle,
                prompt_id=prompt.prompt_id,
                prompt_version=prompt.version,
                prompt_checksum=prompt.checksum,
                provider_id=response.provider_id,
                model_id=response.model_id,
                requested_provider_id=response.requested_provider_id or response.provider_id,
                requested_model_id=response.requested_model_id or response.model_id,
                routing_policy_id=response.routing_policy_id,
                routing_policy_version=response.routing_policy_version,
                evidence_pack_ids=request.approved_context.evidence_ids,
                raw_response_artifact=raw_artifact,
                structured_artifact=None,
                artifact_lineage=(raw_artifact.artifact.artifact_id,),
            ),
            validation_findings=tuple(findings),
            outline_hash=outline_hash,
            evidence_ids=evidence_ids,
            status=status,
            confidence=confidence,
        )
        return structured, tuple(findings)

    def _status(self, request: BlueprintRequest, findings: list[BlueprintValidationFinding]) -> str:
        if any(finding.severity in {"error", "blocking"} for finding in findings):
            return "invalid"
        if request.draft_mode and not request.approved:
            return "draft"
        return "complete"

    def _artifact_lineage(
        self,
        request: BlueprintRequest,
        raw_artifact: ArtifactRecord,
        structured_artifact: ArtifactRecord,
    ) -> tuple[str, ...]:
        lineage: list[str] = []
        for record in request.approved_context.all_records():
            lineage.append(record.artifact.artifact_id)
            lineage.extend(record.parent_artifact_ids)
        lineage.append(raw_artifact.artifact.artifact_id)
        lineage.extend(raw_artifact.parent_artifact_ids)
        lineage.append(structured_artifact.artifact.artifact_id)
        lineage.extend(structured_artifact.parent_artifact_ids)
        return tuple(dict.fromkeys(item for item in lineage if item))

    def _summarise_changes(
        self,
        previous: BlueprintVersionRecord | None,
        request: BlueprintRequest,
        bundle: BlueprintCanonBundle,
        prompt: PromptVersion,
        response: BlueprintEngineResponse,
        structured_blueprint: StructuredBlueprint,
        raw_artifact: ArtifactRecord,
        structured_artifact: ArtifactRecord,
    ) -> tuple[BlueprintChangeSummary, ...]:
        if previous is None:
            return ()
        changes: list[BlueprintChangeSummary] = []
        comparisons = (
            ("input_checksum", previous.input_checksum, request.request_checksum(), "Approved context changed."),
            ("canon_bundle", previous.canon_bundle.to_dict(), bundle.to_dict(), "Canonical bundle changed."),
            ("prompt_version", previous.prompt_version, prompt.version, "Prompt version changed."),
            ("prompt_checksum", previous.prompt_checksum, prompt.checksum, "Prompt content changed."),
            ("provider_id", previous.provider_id, response.provider_id, "Provider changed."),
            ("model_id", previous.model_id, response.model_id, "Model changed."),
            ("requested_provider_id", previous.requested_provider_id, response.requested_provider_id, "Requested provider changed."),
            ("requested_model_id", previous.requested_model_id, response.requested_model_id, "Requested model changed."),
            ("routing_policy_id", previous.routing_policy_id, response.routing_policy_id, "Routing policy changed."),
            ("routing_policy_version", previous.routing_policy_version, response.routing_policy_version, "Routing policy version changed."),
            ("status", previous.status, structured_blueprint.status, "Validation status changed."),
            ("outline_hash", previous.structured_blueprint.outline_hash, structured_blueprint.outline_hash, "Blueprint outline changed."),
            ("raw_response_checksum", previous.raw_response_artifact.artifact.checksum, raw_artifact.artifact.checksum, "Raw response changed."),
            ("structured_checksum", previous.structured_artifact.artifact.checksum, structured_artifact.artifact.checksum, "Structured blueprint changed."),
            ("evidence_ids", list(previous.structured_blueprint.evidence_ids), list(structured_blueprint.evidence_ids), "Evidence references changed."),
        )
        for field, before, after, reason in comparisons:
            if before != after:
                changes.append(BlueprintChangeSummary(field=field, before=before, after=after, reason=reason))
        return tuple(changes)


def _load_records(items: Any) -> tuple[ArtifactRecord, ...]:
    if not items:
        return ()
    records: list[ArtifactRecord] = []
    for item in items:
        if isinstance(item, ArtifactRecord):
            records.append(item)
            continue
        if not isinstance(item, Mapping):
            raise ValueError("artifact records must be objects")
        records.append(ArtifactRecord.from_dict(dict(item)))
    return tuple(records)


def _load_sections(items: list[dict[str, Any]]) -> tuple[BlueprintSection, ...]:
    return tuple(
        BlueprintSection(
            heading=str(item.get("heading", "")),
            level=int(item.get("level", 1)),
            body=_normalise_text_blob(str(item.get("body", ""))),
            children=_load_sections(item.get("children") or []),
        )
        for item in items
    )


def _load_findings(items: list[dict[str, Any]]) -> tuple[BlueprintValidationFinding, ...]:
    return tuple(
        BlueprintValidationFinding(
            code=str(item.get("code", "")),
            severity=str(item.get("severity", "info")),
            message=str(item.get("message", "")),
            location=str(item.get("location", "")),
            evidence_ids=tuple(item.get("evidence_ids") or ()),
            artifact_ids=tuple(item.get("artifact_ids") or ()),
            details=dict(item.get("details") or {}),
        )
        for item in items
    )


def _parse_markdown_sections(text: str) -> tuple[BlueprintSection, ...]:
    heading_re = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
    root: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = [{"level": 0, "children": root, "body": []}]
    for line in text.splitlines():
        match = heading_re.match(line)
        if match:
            level = len(match.group(1))
            heading = match.group(2).strip()
            node = {"heading": heading, "level": level, "body": [], "children": []}
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            stack[-1]["children"].append(node)
            stack.append(node)
            continue
        stack[-1]["body"].append(line)
    return _load_sections(
        [
            {
                "heading": item["heading"],
                "level": item["level"],
                "body": _normalise_text_blob("\n".join(item["body"]).strip("\n")),
                "children": item["children"],
            }
            for item in root
        ]
    )


def _evidence_ids(text: str) -> tuple[str, ...]:
    marker_re = re.compile(r"\bev_[A-Za-z0-9_:-]+\b")
    return tuple(dict.fromkeys(marker_re.findall(text)))


def _normalise_heading(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def _normalise_text_blob(text: str) -> str:
    value = str(text or "")
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return value
        if isinstance(parsed, (list, tuple)):
            parts = [str(item).strip() for item in parsed if str(item).strip()]
            if parts:
                return "\n".join(parts)
    return value


def _split_paragraphs(text: str) -> tuple[str, ...]:
    text = _normalise_text_blob(text)
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


def _parse_slide_heading(heading: str) -> tuple[int | None, str]:
    text = str(heading).strip()
    match = re.match(r"^(?:slide\s+)?(?P<number>\d+)\s*[—-]\s*(?P<name>.*\S)\s*$", text, re.IGNORECASE)
    if match is None:
        malformed = re.match(
            r"^(?:slide\s+)?(?P<number>\d+)(?P<suffix>[A-Za-z0-9.]+)\s*[—-]\s*(?P<name>.*\S)\s*$",
            text,
            re.IGNORECASE,
        )
        if malformed is not None:
            return None, malformed.group("name").strip()
        return None, text
    return int(match.group("number")), match.group("name").strip()


def _section_payload(section: BlueprintSection) -> dict[str, Any]:
    return {
        "heading": section.heading,
        "level": section.level,
        "body": section.body,
        "children": [_section_payload(child) for child in section.children],
    }


def _extension_to_section(heading: str, value: Any) -> BlueprintSection:
    if isinstance(value, BlueprintSection):
        return value
    if isinstance(value, Mapping):
        return BlueprintSection(
            heading=str(heading).strip(),
            level=int(value.get("level", 4)),
            body=_normalise_text_blob(str(value.get("body", ""))),
            children=_load_sections(value.get("children") or []),
        )
    if isinstance(value, (list, tuple)):
        body = "\n".join(str(item) for item in value if str(item).strip())
        return BlueprintSection(str(heading).strip(), 4, body, ())
    return BlueprintSection(str(heading).strip(), 4, str(value).strip(), ())


def _parse_source_notes(section: BlueprintSection) -> tuple[SourceNote, ...]:
    lines: list[str] = []
    body = _normalise_text_blob(section.body)
    if body.strip():
        lines.extend(body.splitlines())
    for child in section.children:
        child_body = _normalise_text_blob(child.body)
        if child_body.strip() or child.children:
            lines.append(child_body if child_body.strip() else child.heading)
    notes: list[SourceNote] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text[:1] in {"-", "*", "•"}:
            text = text[1:].strip()
        evidence_ids = tuple(dict.fromkeys(_evidence_ids(text)))
        evidence_refs = tuple(
            EvidenceReference(
                evidence_id=evidence_id,
                source_note=text,
            )
            for evidence_id in evidence_ids
        )
        notes.append(
            SourceNote(
                text=text,
                evidence_ids=evidence_ids,
                evidence_references=evidence_refs,
            )
        )
    return tuple(notes)


def _parse_slide_content(
    slide_node: BlueprintSection,
    *,
    legacy_mode: bool,
) -> tuple[SlideContent, tuple[ValidationFinding, ...]]:
    thesis: list[str] = []
    founder_insight: list[str] = []
    so_what: list[str] = []
    source_notes: list[SourceNote] = []
    visual_direction: list[str] = []
    speaker_notes: list[str] = []
    evidence_refs: list[EvidenceReference] = []
    extensions: dict[str, Any] = {}
    findings: list[ValidationFinding] = []
    canonical_sections = {
        "thesis": "thesis",
        "founder insight": "founder_insight",
        "so what": "so_what",
        "implication": "so_what",
        "source notes": "source_notes",
        "visual layout direction": "visual_direction",
        "visual direction": "visual_direction",
        "speaker notes": "speaker_notes",
    }

    for section in slide_node.children:
        key = canonical_sections.get(_normalise_heading(section.heading))
        if key == "thesis":
            thesis.extend(_split_paragraphs(section.body) or (section.body.strip(),))
            continue
        if key == "founder_insight":
            founder_insight.extend(_split_paragraphs(section.body) or (section.body.strip(),))
            continue
        if key == "so_what":
            so_what.extend(_split_paragraphs(section.body) or (section.body.strip(),))
            continue
        if key == "source_notes":
            parsed = _parse_source_notes(section)
            source_notes.extend(parsed)
            for note in parsed:
                evidence_refs.extend(note.evidence_references)
            continue
        if key == "visual_direction":
            visual_direction.extend(_split_paragraphs(section.body) or (section.body.strip(),))
            continue
        if key == "speaker_notes":
            speaker_notes.extend(_split_paragraphs(section.body) or (section.body.strip(),))
            continue
        extensions[section.heading] = _section_payload(section)

    if legacy_mode and "Thesis" in extensions:
        findings.append(
            ValidationFinding(
                code="legacy_slide_alias",
                severity="info",
                message="Legacy slide sections were preserved as Blueprint extensions.",
                location=f"slide.{slide_node.heading}",
                details={"source_heading": slide_node.heading},
            )
        )
    if slide_node.body.strip():
        body_paragraphs = _split_paragraphs(slide_node.body) or (slide_node.body.strip(),)
        extensions["body"] = body_paragraphs
        if not any((thesis, founder_insight, so_what, source_notes, visual_direction, speaker_notes)):
            thesis.extend(body_paragraphs)
            findings.append(
                ValidationFinding(
                    code="slide_body_preserved",
                    severity="info",
                    message="Slide body text was preserved in the structured thesis field.",
                    location=f"slide.{slide_node.heading}",
                )
            )

    content = SlideContent(
        thesis=tuple(thesis),
        founder_insight=tuple(founder_insight),
        so_what=tuple(so_what),
        source_notes=tuple(source_notes),
        visual_direction=tuple(visual_direction),
        speaker_notes=tuple(speaker_notes),
        evidence_references=_unique_evidence_references(evidence_refs),
        extensions=extensions,
    )
    return content, tuple(findings)


@dataclass(frozen=True, slots=True)
class _ParsedSlideCandidate:
    node: BlueprintSection
    slide_no: int | None
    slide_name: str
    source_act_name: str


def _is_act_heading(heading: str) -> bool:
    return _normalise_heading(heading).startswith("act ")


def _unpack_response_sections(sections: tuple[BlueprintSection, ...]) -> tuple[str, tuple[BlueprintSection, ...]]:
    if not sections:
        return "", ()
    first = sections[0]
    if first.level == 1:
        title = first.heading
        if first.children:
            return title, first.children
        return title, tuple(sections[1:])
    return "", sections


def _collect_slide_candidates(
    sections: tuple[BlueprintSection, ...],
    current_act: str = "",
) -> tuple[_ParsedSlideCandidate, ...]:
    candidates: list[_ParsedSlideCandidate] = []
    for section in sections:
        slide_no, slide_name = _parse_slide_heading(section.heading)
        if slide_no is not None or re.match(
            r"^(?:slide\s+)?\d+\S*",
            str(section.heading).strip(),
            re.IGNORECASE,
        ):
            candidates.append(
                _ParsedSlideCandidate(
                    node=section,
                    slide_no=slide_no,
                    slide_name=slide_name,
                    source_act_name=current_act,
                )
            )
            continue
        next_act = current_act
        if _is_act_heading(section.heading):
            next_act = section.heading
        candidates.extend(_collect_slide_candidates(section.children, next_act))
    return tuple(candidates)


def _canonical_act_name_for_slide(schema: BlueprintSchemaV3, slide: BlueprintSchemaSlide) -> str:
    if slide.slide_no == 1 or _normalise_heading(slide.act) in {"title", "cover"}:
        return schema.acts[0]
    for act_name in schema.acts:
        if _normalise_heading(act_name) == _normalise_heading(slide.act):
            return act_name
    return schema.acts[0]


def _canonicalise_blueprint_response(
    *,
    schema: BlueprintSchemaV3,
    roots: tuple[BlueprintSection, ...],
    raw_candidates: tuple[_ParsedSlideCandidate, ...],
    evidence_ids: tuple[str, ...],
    request: BlueprintRequest,
    legacy_mode: bool,
) -> tuple[tuple[BlueprintAct, ...], tuple[BlueprintValidationFinding, ...]]:
    by_no: dict[int, list[_ParsedSlideCandidate]] = {}
    by_name: dict[str, list[_ParsedSlideCandidate]] = {}
    for candidate in raw_candidates:
        if candidate.slide_no is not None:
            by_no.setdefault(candidate.slide_no, []).append(candidate)
        if candidate.slide_name:
            by_name.setdefault(_normalise_heading(candidate.slide_name), []).append(candidate)

    findings: list[BlueprintValidationFinding] = []
    canonical_acts: list[BlueprintAct] = []
    schema_slides_by_act: dict[str, list[BlueprintSchemaSlide]] = {}
    for slide in schema.slides:
        schema_slides_by_act.setdefault(_canonical_act_name_for_slide(schema, slide), []).append(slide)

    observed_slide_numbers = {candidate.slide_no for candidate in raw_candidates if candidate.slide_no is not None}
    canonical_slide_numbers = {slide.slide_no for slide in schema.slides}
    extra_slides = sorted(number for number in observed_slide_numbers if number not in canonical_slide_numbers)
    if extra_slides:
        findings.append(
            BlueprintValidationFinding(
                code="extra_slide_numbers_present",
                severity="warning",
                message="The response contained slide numbers outside the canonical schema.",
                location="raw_response",
                details={"extra_slide_numbers": extra_slides},
            )
        )

    for act_index, act_name in enumerate(schema.acts, start=1):
        act_slides: list[BlueprintSlide] = []
        act_findings: list[BlueprintValidationFinding] = []
        source_act_names: list[str] = []
        for schema_slide in schema_slides_by_act.get(act_name, []):
            candidates = by_no.get(schema_slide.slide_no, [])
            matched_by = "number"
            if not candidates:
                candidates = by_name.get(_normalise_heading(schema_slide.slide_name), [])
                matched_by = "name"
            selected = candidates[0] if candidates else None
            slide_findings: list[BlueprintValidationFinding] = []
            if selected is None:
                slide_content = SlideContent()
                source_slide_name = ""
                source_act_name = ""
                extensions = {
                    "expected_schema_slide": schema_slide.to_dict(),
                    "missing": True,
                }
                slide_findings.append(
                    BlueprintValidationFinding(
                        code="missing_slide",
                        severity="warning" if legacy_mode else "blocking",
                        message="The canonical slide is missing from the response.",
                        location=f"slide.{schema_slide.slide_no}",
                        details={
                            "expected_slide_no": schema_slide.slide_no,
                            "expected_slide_name": schema_slide.slide_name,
                            "expected_act": act_name,
                        },
                    )
                )
            else:
                slide_content, content_findings = _parse_slide_content(selected.node, legacy_mode=False)
                slide_findings.extend(content_findings)
                source_slide_name = selected.node.heading
                source_act_name = selected.source_act_name
                extensions = dict(slide_content.extensions)
                extensions["source_candidates"] = [_section_payload(candidate.node) for candidate in candidates]
                extensions["matched_by"] = matched_by
                extensions["selected_source_heading"] = selected.node.heading
                if source_act_name:
                    extensions["selected_source_act"] = source_act_name
                if len(candidates) > 1:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="duplicate_slide",
                            severity="error",
                            message="Multiple sections matched the same canonical slide.",
                            location=f"slide.{schema_slide.slide_no}",
                            details={
                                "candidate_count": len(candidates),
                                "candidate_headings": [candidate.node.heading for candidate in candidates],
                            },
                        )
                    )
                    extensions["duplicate_source_sections"] = [
                        _section_payload(candidate.node) for candidate in candidates[1:]
                    ]
                if matched_by == "name" and _extract_slide_number(selected.node.heading) is None:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="malformed_slide_number",
                            severity="warning",
                            message="The response matched a slide by name because the slide number was missing or malformed.",
                            location=f"slide.{schema_slide.slide_no}",
                            details={
                                "expected_slide_no": schema_slide.slide_no,
                                "selected_heading": selected.node.heading,
                            },
                        )
                    )
                if _normalise_heading(schema_slide.slide_name) != _normalise_heading(selected.slide_name):
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="canonical_slide_name_mismatch",
                            severity="warning",
                            message="The matched slide name differs from the canonical schema name.",
                            location=f"slide.{schema_slide.slide_no}",
                            details={
                                "expected_slide_name": schema_slide.slide_name,
                                "observed_slide_name": selected.slide_name,
                            },
                        )
                    )
                if source_act_name and _normalise_heading(source_act_name) != _normalise_heading(act_name):
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="wrong_act_membership",
                            severity="warning" if legacy_mode else "error",
                            message="The slide appeared under the wrong act in the raw response.",
                            location=f"slide.{schema_slide.slide_no}",
                            details={
                                "expected_act": act_name,
                                "observed_act": source_act_name,
                            },
                        )
                    )
                if slide_content.founder_insight:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="founder_insight_retained",
                            severity="info",
                            message="Founder Insight content was retained in the structured slide.",
                            location=f"slide.{schema_slide.slide_no}",
                        )
                    )
                if slide_content.so_what:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="so_what_retained",
                            severity="info",
                            message="So What content was retained in the structured slide.",
                            location=f"slide.{schema_slide.slide_no}",
                        )
                    )
                if slide_content.source_notes:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="source_notes_retained",
                            severity="info",
                            message="Source Notes were retained in the structured slide.",
                            location=f"slide.{schema_slide.slide_no}",
                        )
                    )
                if slide_content.visual_direction:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="visual_direction_retained",
                            severity="info",
                            message="Visual direction was retained in the structured slide.",
                            location=f"slide.{schema_slide.slide_no}",
                        )
                    )

            content_checks = {
                "thesis": bool(slide_content.thesis),
                "founder insight": bool(slide_content.founder_insight),
                "so what": bool(slide_content.so_what),
                "source notes": bool(slide_content.source_notes),
                "visual / layout direction": bool(slide_content.visual_direction),
                "visual direction": bool(slide_content.visual_direction),
                "speaker notes": bool(slide_content.speaker_notes),
            }
            for requirement in schema_slide.content_requirements:
                requirement_key = _normalise_heading(requirement)
                if requirement_key in content_checks and not content_checks[requirement_key]:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="missing_content_requirement",
                            severity="warning" if legacy_mode else "error",
                            message="A canonical slide content requirement was not present in the response.",
                            location=f"slide.{schema_slide.slide_no}",
                            details={
                                "required": requirement,
                                "slide_no": schema_slide.slide_no,
                                "slide_name": schema_slide.slide_name,
                            },
                        )
                    )

            if schema_slide.slide_no == 12:
                combined_text = " ".join(
                    [
                        " ".join(slide_content.thesis),
                        " ".join(slide_content.founder_insight),
                        " ".join(slide_content.so_what),
                        " ".join(note.text for note in slide_content.source_notes),
                    ]
                ).lower()
                if any(token in combined_text for token in (" men ", " women ", " age ", " income ")):
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="behavioural_demand_pool_rule",
                            severity="warning",
                            message="Demand pools should read as behavioural discoveries, not demographic labels.",
                            location=f"slide.{schema_slide.slide_no}",
                        )
                    )

            if schema_slide.slide_no == 27 and not slide_content.visual_direction:
                slide_findings.append(
                    BlueprintValidationFinding(
                        code="slide_27_visual_direction_missing",
                        severity="warning" if legacy_mode else "error",
                        message="Slide 27 must retain a visual or layout direction cue.",
                        location="slide.27",
                    )
                )
            if schema_slide.slide_no == 28:
                combined_text = " ".join(
                    [
                        " ".join(slide_content.thesis),
                        " ".join(slide_content.founder_insight),
                        " ".join(slide_content.so_what),
                        " ".join(note.text for note in slide_content.source_notes),
                        " ".join(slide_content.visual_direction),
                        " ".join(slide_content.speaker_notes),
                    ]
                ).lower()
                if "growth priorities" not in combined_text and "dependencies" not in combined_text:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="slide_28_growth_priorities_dependencies_missing",
                            severity="warning" if legacy_mode else "error",
                            message="Slide 28 should distinguish growth priorities from dependencies.",
                            location="slide.28",
                        )
                    )
            if schema_slide.slide_no == 29:
                if not slide_content.source_notes:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="slide_29_measurement_sources_missing",
                            severity="warning" if legacy_mode else "error",
                            message="Slide 29 must retain measurement source notes.",
                            location="slide.29",
                        )
                    )
                if not slide_content.so_what:
                    slide_findings.append(
                        BlueprintValidationFinding(
                            code="slide_29_learning_summary_missing",
                            severity="warning" if legacy_mode else "error",
                            message="Slide 29 must retain the learning summary.",
                            location="slide.29",
                        )
                    )

            if slide_content.extensions.get("body"):
                slide_findings.append(
                    BlueprintValidationFinding(
                        code="slide_body_preserved",
                        severity="info",
                        message="Slide body text was preserved in the structured extensions.",
                        location=f"slide.{schema_slide.slide_no}",
                    )
                )

            slide_confidence = _confidence_from_findings(tuple(slide_findings))
            act_slides.append(
                BlueprintSlide(
                    slide_no=schema_slide.slide_no,
                    slide_name=schema_slide.slide_name,
                    act=act_name,
                    purpose=schema_slide.purpose,
                    visual_type=schema_slide.visual_type,
                    layout_type=schema_slide.layout_type,
                    content_requirements=schema_slide.content_requirements,
                    inputs=schema_slide.inputs,
                    outputs=schema_slide.outputs,
                    so_what_test=schema_slide.so_what_test,
                    content=slide_content,
                    confidence=slide_confidence,
                    validation_findings=tuple(slide_findings),
                    source_slide_name=source_slide_name,
                    source_act_name=source_act_name,
                    extensions=extensions,
                )
            )
            act_findings.extend(slide_findings)
            findings.extend(
                finding for finding in slide_findings if finding.severity != "info"
            )
            if source_act_name:
                source_act_names.append(source_act_name)
        act_confidence = _confidence_from_findings(tuple(act_findings))
        canonical_acts.append(
            BlueprintAct(
                act_no=act_index,
                act_name=act_name,
                slides=tuple(act_slides),
                confidence=act_confidence,
                validation_findings=tuple(act_findings),
                source_act_name=source_act_names[0] if source_act_names else act_name,
                extensions={
                    "schema_slide_numbers": [slide.slide_no for slide in act_slides],
                    "source_act_names": list(dict.fromkeys(source_act_names)),
                },
            )
        )

    if len(canonical_acts) != len(schema.acts):
        findings.append(
            BlueprintValidationFinding(
                code="schema_act_count_mismatch",
                severity="blocking",
                message="The response did not map to all six canonical acts.",
                location="raw_response",
                details={
                    "expected_acts": len(schema.acts),
                    "observed_acts": len(canonical_acts),
                },
            )
        )

    observed_slide_count = len(raw_candidates)
    if observed_slide_count != len(schema.slides):
        findings.append(
            BlueprintValidationFinding(
                code="schema_slide_count_mismatch",
                severity="warning" if observed_slide_count > 0 else "blocking",
                message="The response did not map cleanly to the canonical 30-slide schema.",
                location="raw_response",
                details={
                    "expected_slides": len(schema.slides),
                    "observed_slides": observed_slide_count,
                },
            )
        )

    return tuple(canonical_acts), tuple(findings)


def _unique_evidence_references(items: Sequence[EvidenceReference]) -> tuple[EvidenceReference, ...]:
    unique: list[EvidenceReference] = []
    seen: set[str] = set()
    for reference in items:
        if reference.evidence_id in seen:
            continue
        seen.add(reference.evidence_id)
        unique.append(reference)
    return tuple(unique)


def _confidence_from_findings(findings: tuple[ValidationFinding, ...]) -> float:
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


def _load_lineage(data: Mapping[str, Any]) -> BlueprintLineage:
    lineage_source = data.get("lineage") if isinstance(data.get("lineage"), Mapping) else data
    canon_bundle_data = lineage_source.get("canon_bundle") or data.get("canon_bundle") or {}
    raw_response_artifact_data = lineage_source.get("raw_response_artifact") or data.get("raw_response_artifact")
    structured_artifact_data = lineage_source.get("structured_artifact") or data.get("structured_artifact")
    if raw_response_artifact_data is None:
        raise ValueError("blueprint lineage must contain a raw response artifact")
    raw_response_artifact = ArtifactRecord.from_dict(dict(raw_response_artifact_data))
    structured_artifact = (
        ArtifactRecord.from_dict(dict(structured_artifact_data))
        if structured_artifact_data is not None
        else None
    )
    return BlueprintLineage(
        canon_bundle=BlueprintCanonBundle(
            bundle_id=str(canon_bundle_data["bundle_id"]),
            version=str(canon_bundle_data["version"]),
            status=str(canon_bundle_data.get("status", "active")),
            prompt_asset_id=str(canon_bundle_data["prompt_asset_id"]),
            supporting_asset_ids=tuple(canon_bundle_data.get("supporting_asset_ids") or ()),
            components=tuple(
                BlueprintCanonBundleComponent(
                    asset_id=str(component["asset_id"]),
                    version=str(component["version"]),
                    checksum=str(component["checksum"]),
                    repository_path=str(component["repository_path"]),
                )
                for component in canon_bundle_data.get("components") or []
            ),
            checksum=str(canon_bundle_data.get("checksum", "")),
            compatibility_notes=tuple(canon_bundle_data.get("compatibility_notes") or ()),
        ),
        prompt_id=str(lineage_source.get("prompt_id", data.get("prompt_id", ""))),
        prompt_version=int(lineage_source.get("prompt_version", data.get("prompt_version", 1))),
        prompt_checksum=str(lineage_source.get("prompt_checksum", data.get("prompt_checksum", ""))),
        provider_id=str(lineage_source.get("provider_id", data.get("provider_id", ""))),
        model_id=str(lineage_source.get("model_id", data.get("model_id", ""))),
        requested_provider_id=str(lineage_source.get("requested_provider_id", data.get("requested_provider_id", data.get("provider_id", "")))),
        requested_model_id=str(lineage_source.get("requested_model_id", data.get("requested_model_id", data.get("model_id", "")))),
        routing_policy_id=str(lineage_source.get("routing_policy_id", data.get("routing_policy_id", ""))),
        routing_policy_version=str(lineage_source.get("routing_policy_version", data.get("routing_policy_version", ""))),
        evidence_pack_ids=tuple(lineage_source.get("evidence_pack_ids") or data.get("evidence_pack_ids") or ()),
        raw_response_artifact=raw_response_artifact,
        structured_artifact=structured_artifact,
        artifact_lineage=tuple(lineage_source.get("artifact_lineage") or data.get("artifact_lineage") or ()),
        extensions=dict(lineage_source.get("extensions") or data.get("extensions") or {}),
    )


def _load_acts(items: Any) -> tuple[BlueprintAct, ...]:
    if not items:
        return ()
    acts: list[BlueprintAct] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, BlueprintAct):
            acts.append(item)
            continue
        if not isinstance(item, Mapping):
            raise ValueError("blueprint acts must be objects")
        slides_data = item.get("slides")
        if slides_data is None:
            slides_data = item.get("children") or []
        slides = _load_slides(slides_data)
        acts.append(
            BlueprintAct(
                act_no=int(item.get("act_no", index)),
                act_name=str(item.get("act_name", item.get("heading", ""))).strip(),
                slides=slides,
                confidence=float(item.get("confidence", 1.0)),
                validation_findings=_load_findings(item.get("validation_findings") or []),
                source_act_name=str(item.get("source_act_name", item.get("heading", ""))).strip(),
                extensions=dict(item.get("extensions") or {}),
            )
        )
    return tuple(acts)


def _load_slides(items: Any) -> tuple[BlueprintSlide, ...]:
    if not items:
        return ()
    slides: list[BlueprintSlide] = []
    for item in items:
        if isinstance(item, BlueprintSlide):
            slides.append(item)
            continue
        if not isinstance(item, Mapping):
            raise ValueError("blueprint slides must be objects")
        if "content" in item:
            content = _load_slide_content(item.get("content") or {})
            findings = _load_findings(item.get("validation_findings") or [])
            slides.append(
                BlueprintSlide(
                    slide_no=int(item["slide_no"]),
                    slide_name=str(item["slide_name"]).strip(),
                    act=str(item["act"]).strip(),
                    purpose=str(item.get("purpose", "")).strip(),
                    visual_type=str(item.get("visual_type", "")).strip(),
                    layout_type=str(item.get("layout_type", "")).strip(),
                    content_requirements=tuple(item.get("content_requirements") or ()),
                    inputs=tuple(item.get("inputs") or ()),
                    outputs=tuple(item.get("outputs") or ()),
                    so_what_test=str(item.get("so_what_test", "")).strip(),
                    content=content,
                    confidence=float(item.get("confidence", 1.0)),
                    validation_findings=findings,
                    source_slide_name=str(item.get("source_slide_name", "")).strip(),
                    source_act_name=str(item.get("source_act_name", "")).strip(),
                    extensions=dict(item.get("extensions") or {}),
                )
            )
            continue
        content, content_findings = _parse_slide_content(
            _load_section_node(item),
            legacy_mode=True,
        )
        findings = tuple(content_findings) + _load_findings(item.get("validation_findings") or [])
        slides.append(
            BlueprintSlide(
                slide_no=int(item.get("slide_no") or _extract_slide_number(item.get("heading", "")) or 0),
                slide_name=str(item.get("slide_name", _extract_slide_name(item.get("heading", "")))).strip(),
                act=str(item.get("act", "")).strip(),
                purpose=str(item.get("purpose", "")).strip(),
                visual_type=str(item.get("visual_type", "")).strip(),
                layout_type=str(item.get("layout_type", "")).strip(),
                content_requirements=tuple(item.get("content_requirements") or ()),
                inputs=tuple(item.get("inputs") or ()),
                outputs=tuple(item.get("outputs") or ()),
                so_what_test=str(item.get("so_what_test", "")).strip(),
                content=content,
                confidence=float(item.get("confidence", 1.0)),
                validation_findings=findings,
                source_slide_name=str(item.get("source_slide_name", item.get("heading", ""))).strip(),
                source_act_name=str(item.get("source_act_name", "")).strip(),
                extensions=dict(item.get("extensions") or {}),
            )
        )
    return tuple(slides)


def _load_slide_content(data: Mapping[str, Any]) -> SlideContent:
    if isinstance(data, SlideContent):
        return data
    if not isinstance(data, Mapping):
        raise ValueError("slide content must be an object")
    return SlideContent(
        thesis=tuple(data.get("thesis") or ()),
        founder_insight=tuple(data.get("founder_insight") or ()),
        so_what=tuple(data.get("so_what") or ()),
        source_notes=tuple(
            SourceNote(
                text=str(item.get("text", "")).strip(),
                evidence_ids=tuple(item.get("evidence_ids") or ()),
                evidence_references=tuple(
                    EvidenceReference(
                        evidence_id=str(reference.get("evidence_id", "")).strip(),
                        source_note=str(reference.get("source_note", "")).strip(),
                        slide_no=(
                            int(reference["slide_no"])
                            if reference.get("slide_no") is not None
                            else None
                        ),
                        slide_name=str(reference.get("slide_name", "")).strip(),
                        claim=str(reference.get("claim", "")).strip(),
                        confidence=float(reference.get("confidence", 1.0)),
                        extensions=dict(reference.get("extensions") or {}),
                    )
                    for reference in item.get("evidence_references") or []
                ),
                extensions=dict(item.get("extensions") or {}),
            )
            for item in data.get("source_notes") or []
        ),
        visual_direction=tuple(data.get("visual_direction") or ()),
        speaker_notes=tuple(data.get("speaker_notes") or ()),
        evidence_references=tuple(
            EvidenceReference(
                evidence_id=str(item.get("evidence_id", "")).strip(),
                source_note=str(item.get("source_note", "")).strip(),
                slide_no=(int(item["slide_no"]) if item.get("slide_no") is not None else None),
                slide_name=str(item.get("slide_name", "")).strip(),
                claim=str(item.get("claim", "")).strip(),
                confidence=float(item.get("confidence", 1.0)),
                extensions=dict(item.get("extensions") or {}),
            )
            for item in data.get("evidence_references") or []
        ),
        extensions=dict(data.get("extensions") or {}),
    )


def _load_section_node(item: Mapping[str, Any]) -> BlueprintSection:
    return BlueprintSection(
        heading=str(item.get("heading", "")),
        level=int(item.get("level", 1)),
        body=_normalise_text_blob(str(item.get("body", ""))),
        children=_load_sections(item.get("children") or []),
    )


def _load_section_tree(items: list[dict[str, Any]]) -> tuple[BlueprintSection, ...]:
    return tuple(_load_section_node(item) for item in items)


def _extract_slide_number(heading: str) -> int | None:
    number, _ = _parse_slide_heading(heading)
    return number


def _extract_slide_name(heading: str) -> str:
    _, name = _parse_slide_heading(heading)
    return name
