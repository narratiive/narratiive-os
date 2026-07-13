from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from .artifact_catalog import ArtifactRecord, FileArtifactCatalog
from .execution_package import ExecutionPackage
from .prompt_registry import FilePromptRegistry, PromptVersion
from .provider import ProviderClient
from .research_engine import sha256_hex, slugify, utc_now


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_ID = "claude-growth-blueprint"
DEFAULT_PROMPT_SOURCE = REPO_ROOT / "templates" / "Growth_Blueprint.md"
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
        if severity not in {"info", "warning", "error"}:
            raise ValueError("severity must be info, warning, or error")
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
    request_id: str
    workspace_id: str
    client_id: str
    document_title: str
    raw_response: str
    sections: tuple[BlueprintSection, ...]
    validation_findings: tuple[BlueprintValidationFinding, ...]
    outline_hash: str
    evidence_ids: tuple[str, ...]
    status: str
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _safe_identifier(self.blueprint_id, "blueprint_id")
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "document_title": self.document_title,
            "raw_response": self.raw_response,
            "sections": [section.to_dict() for section in self.sections],
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "outline_hash": self.outline_hash,
            "evidence_ids": list(self.evidence_ids),
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class BlueprintEngineResponse:
    raw_response: str
    provider_id: str
    model_id: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.provider_id, "provider_id")
        _safe_identifier(self.model_id, "model_id")
        _safe_identifier(self.prompt_id, "prompt_id")
        object.__setattr__(self, "provider_metadata", dict(self.provider_metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_response": self.raw_response,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
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
        structured_blueprint = data.get("structured_blueprint") or {}
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
            structured_blueprint=StructuredBlueprint(
                blueprint_id=str(structured_blueprint["blueprint_id"]),
                request_id=str(structured_blueprint["request_id"]),
                workspace_id=str(structured_blueprint["workspace_id"]),
                client_id=str(structured_blueprint["client_id"]),
                document_title=str(structured_blueprint.get("document_title", "")),
                raw_response=str(structured_blueprint["raw_response"]),
                sections=_load_sections(structured_blueprint.get("sections") or []),
                validation_findings=_load_findings(structured_blueprint.get("validation_findings") or []),
                outline_hash=str(structured_blueprint["outline_hash"]),
                evidence_ids=tuple(structured_blueprint.get("evidence_ids") or ()),
                status=str(structured_blueprint.get("status", "complete")),
                created_at=str(structured_blueprint.get("created_at", utc_now())),
            ),
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
        prompt_source_path: str | Path = DEFAULT_PROMPT_SOURCE,
        prompt_id: str = DEFAULT_PROMPT_ID,
        stage_id: str = DEFAULT_STAGE_ID,
        agent_id: str = DEFAULT_AGENT_ID,
        expected_provider_id: str = "anthropic",
        expected_model_id: str = "claude-sonnet-4-5",
    ) -> None:
        self.provider = provider
        self.prompt_registry = prompt_registry
        self.prompt_source_path = Path(prompt_source_path)
        self.prompt_id = prompt_id
        self.stage_id = stage_id
        self.agent_id = agent_id
        self.expected_provider_id = expected_provider_id
        self.expected_model_id = expected_model_id

    def generate(self, request: BlueprintRequest, prompt: PromptVersion) -> BlueprintEngineResponse:
        package = ExecutionPackage(
            schema_version=1,
            job_id=request.request_id,
            run_id=request.blueprint_id,
            stage_id=self.stage_id,
            agent_id=self.agent_id,
            agent_version=str(prompt.version),
            agent_ref=str(self.prompt_source_path),
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
        provider_id = str(response.metadata.get("provider_id") if response.metadata else self.expected_provider_id)
        model_id = str(response.metadata.get("model_id") if response.metadata else self.expected_model_id)
        if provider_id != self.expected_provider_id:
            provider_id = self.expected_provider_id
        if model_id != self.expected_model_id:
            model_id = self.expected_model_id
        return BlueprintEngineResponse(
            raw_response=response.content,
            provider_id=provider_id,
            model_id=model_id,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            provider_metadata=dict(response.metadata or {}),
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
                "source_path": str(self.prompt_source_path),
            },
            "engine": {
                "name": self.name,
                "expected_provider_id": self.expected_provider_id,
                "expected_model_id": self.expected_model_id,
            },
        }


class BlueprintBlockedError(RuntimeError):
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
        store: FileBlueprintStore | None = None,
        prompt_source_path: str | Path = DEFAULT_PROMPT_SOURCE,
        prompt_id: str = DEFAULT_PROMPT_ID,
    ) -> None:
        self.artifact_catalog = artifact_catalog
        self.prompt_registry = prompt_registry
        self.engine = engine
        self.store = store or FileBlueprintStore(Path(self.artifact_catalog.root).parent / "blueprints")
        self.prompt_source_path = Path(prompt_source_path)
        self.prompt_id = prompt_id

    def generate(self, request: BlueprintRequest) -> BlueprintVersionRecord:
        self._validate_request(request)
        prompt = self._load_prompt_version()
        response = self.engine.generate(request, prompt)
        structured_blueprint, findings = self._structure_response(request, response)
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
                "request_id": request.request_id,
            },
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
                "request_id": request.request_id,
            },
        )
        previous = self.store.latest(request.workspace_id, request.client_id, request.blueprint_id)
        version = previous.version + 1 if previous else 1
        change_summary = self._summarise_changes(previous, request, prompt, response, structured_blueprint, raw_artifact, structured_artifact)
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
        if not self.prompt_source_path.is_file():
            raise BlueprintBlockedError(f"Blueprint prompt source not found: {self.prompt_source_path}")
        content = self.prompt_source_path.read_text(encoding="utf-8")
        history = self.prompt_registry.history(self.prompt_id)
        if history and history[-1].content == content:
            prompt = history[-1]
        else:
            prompt = self.prompt_registry.publish(
                self.prompt_id,
                content,
                metadata={
                    "source_path": str(self.prompt_source_path),
                    "purpose": "claude_blueprint_orchestration",
                },
            )
        self.prompt_registry.activate(self.prompt_id, prompt.version)
        return prompt

    def _structure_response(
        self,
        request: BlueprintRequest,
        response: BlueprintEngineResponse,
    ) -> tuple[StructuredBlueprint, tuple[BlueprintValidationFinding, ...]]:
        sections = _parse_markdown_sections(response.raw_response)
        document_title = sections[0].heading if sections and sections[0].level == 1 else ""
        display_sections = sections[0].children if document_title and sections[0].children else sections
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
        if not sections:
            findings.append(
                BlueprintValidationFinding(
                    code="missing_outline",
                    severity="error",
                    message="Blueprint response did not contain any markdown sections.",
                    location="raw_response",
                )
            )
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
                    for section in sections
                ]
            )
        )
        status = self._status(request, findings)
        structured = StructuredBlueprint(
            blueprint_id=request.blueprint_id,
            request_id=request.request_id,
            workspace_id=request.workspace_id,
            client_id=request.client_id,
            document_title=document_title,
            raw_response=response.raw_response,
            sections=display_sections,
            validation_findings=tuple(findings),
            outline_hash=outline_hash,
            evidence_ids=evidence_ids,
            status=status,
        )
        return structured, tuple(findings)

    def _status(self, request: BlueprintRequest, findings: list[BlueprintValidationFinding]) -> str:
        if any(finding.severity == "error" for finding in findings):
            return "invalid"
        if request.draft_mode and not request.approved:
            return "draft"
        if findings:
            return "partial"
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
            ("prompt_version", previous.prompt_version, prompt.version, "Prompt version changed."),
            ("prompt_checksum", previous.prompt_checksum, prompt.checksum, "Prompt content changed."),
            ("provider_id", previous.provider_id, response.provider_id, "Provider changed."),
            ("model_id", previous.model_id, response.model_id, "Model changed."),
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
            body=str(item.get("body", "")),
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
                "body": "\n".join(item["body"]).strip("\n"),
                "children": item["children"],
            }
            for item in root
        ]
    )


def _evidence_ids(text: str) -> tuple[str, ...]:
    marker_re = re.compile(r"\bev_[A-Za-z0-9_:-]+\b")
    return tuple(dict.fromkeys(marker_re.findall(text)))
