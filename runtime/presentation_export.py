from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable


def _safe_identifier(value: str, field_name: str) -> str:
    value = str(value).strip()
    if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in value):
        raise ValueError(f"{field_name} must be a safe non-empty identifier")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _checksum(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class PresentationTemplateConfiguration:
    template_id: str
    template_version: str
    destination_folder_id: str
    exporter: str = "claude"

    def __post_init__(self) -> None:
        _safe_identifier(self.template_id, "template_id")
        _safe_identifier(self.template_version, "template_version")
        _safe_identifier(self.destination_folder_id, "destination_folder_id")
        if self.exporter != "claude":
            raise ValueError("only the existing Claude Slides export capability is supported")


@dataclass(frozen=True, slots=True)
class PresentationExportRequest:
    workspace_id: str
    client_id: str
    blueprint_id: str
    blueprint_version: int
    renderable_checksum: str
    canon_version: str
    canon_checksums: Mapping[str, str]
    template: PresentationTemplateConfiguration
    requested_version: int | None = None

    def __post_init__(self) -> None:
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        _safe_identifier(self.blueprint_id, "blueprint_id")
        if self.blueprint_version <= 0:
            raise ValueError("blueprint_version must be positive")
        if self.requested_version is not None and self.requested_version <= 0:
            raise ValueError("requested_version must be positive")
        if len(self.renderable_checksum) != 64:
            raise ValueError("renderable_checksum must be a SHA-256 checksum")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
            "renderable_checksum": self.renderable_checksum,
            "canon_version": self.canon_version,
            "canon_checksums": dict(self.canon_checksums),
            "template_id": self.template.template_id,
            "template_version": self.template.template_version,
            "destination_folder_id": self.template.destination_folder_id,
            "exporter": self.template.exporter,
        }


@dataclass(frozen=True, slots=True)
class PresentationAdapterResult:
    presentation_id: str
    presentation_url: str
    provider: str = "claude"
    provider_request_id: str = ""
    safe_diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.presentation_id, "presentation_id")
        if not self.presentation_url.startswith("https://"):
            raise ValueError("presentation_url must use HTTPS")
        if self.provider != "claude":
            raise ValueError("provider must be claude")


@dataclass(frozen=True, slots=True)
class PresentationExportRecord:
    export_id: str
    version: int
    workspace_id: str
    client_id: str
    status: str
    request_checksum: str
    source_blueprint_id: str
    source_blueprint_version: int
    renderable_checksum: str
    canon_version: str
    canon_checksums: Mapping[str, str]
    template_id: str
    template_version: str
    destination_folder_id: str
    presentation_id: str = ""
    presentation_url: str = ""
    provider: str = "claude"
    provider_request_id: str = ""
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""
    created_at: str = field(default_factory=_utc_now)
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_id": self.export_id,
            "version": self.version,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "status": self.status,
            "request_checksum": self.request_checksum,
            "source_blueprint_id": self.source_blueprint_id,
            "source_blueprint_version": self.source_blueprint_version,
            "renderable_checksum": self.renderable_checksum,
            "canon_version": self.canon_version,
            "canon_checksums": dict(self.canon_checksums),
            "template_id": self.template_id,
            "template_version": self.template_version,
            "destination_folder_id": self.destination_folder_id,
            "presentation_id": self.presentation_id,
            "presentation_url": self.presentation_url,
            "provider": self.provider,
            "provider_request_id": self.provider_request_id,
            "retryable": self.retryable,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PresentationExportRecord":
        return cls(**dict(payload))


@runtime_checkable
class PresentationAdapter(Protocol):
    def export(
        self,
        *,
        request: PresentationExportRequest,
        renderable_blueprint: Mapping[str, Any],
    ) -> PresentationAdapterResult: ...


class ClaudeSlidesAdapter:
    """Delegates deck creation to Claude's existing Google Slides export capability.

    The injected callable is responsible for invoking Claude and returning only safe
    presentation metadata. OAuth tokens, service-account material and API keys never
    cross this boundary or enter persisted records.
    """

    def __init__(
        self,
        export_callable: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        self._export_callable = export_callable

    def export(
        self,
        *,
        request: PresentationExportRequest,
        renderable_blueprint: Mapping[str, Any],
    ) -> PresentationAdapterResult:
        payload = {
            "operation": "export_google_slides",
            "workspace_id": request.workspace_id,
            "client_id": request.client_id,
            "template_id": request.template.template_id,
            "template_version": request.template.template_version,
            "destination_folder_id": request.template.destination_folder_id,
            "blueprint": dict(renderable_blueprint),
            "lineage": request.identity_payload(),
        }
        raw = self._export_callable(payload)
        if not isinstance(raw, Mapping):
            raise ValueError("Claude export returned an invalid response")
        return PresentationAdapterResult(
            presentation_id=str(raw.get("presentation_id", "")).strip(),
            presentation_url=str(raw.get("presentation_url", "")).strip(),
            provider="claude",
            provider_request_id=str(raw.get("provider_request_id", "")).strip(),
            safe_diagnostics=dict(raw.get("safe_diagnostics", {}) or {}),
        )


class FakePresentationAdapter:
    def __init__(self, *, fail: bool = False, retryable: bool = True) -> None:
        self.fail = fail
        self.retryable = retryable
        self.calls: list[dict[str, Any]] = []

    def export(
        self,
        *,
        request: PresentationExportRequest,
        renderable_blueprint: Mapping[str, Any],
    ) -> PresentationAdapterResult:
        self.calls.append({"request": request, "blueprint": dict(renderable_blueprint)})
        if self.fail:
            error = RuntimeError("deterministic adapter failure")
            setattr(error, "retryable", self.retryable)
            raise error
        digest = _checksum(request.identity_payload())[:20]
        return PresentationAdapterResult(
            presentation_id=f"deck-{digest}",
            presentation_url=f"https://docs.google.com/presentation/d/deck-{digest}/edit",
            provider_request_id=f"fake-{digest}",
        )


class FilePresentationExportStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _directory(self, workspace_id: str, client_id: str) -> Path:
        _safe_identifier(workspace_id, "workspace_id")
        _safe_identifier(client_id, "client_id")
        return self.root / "workspaces" / workspace_id / "clients" / client_id / "presentation_exports"

    def list(self, workspace_id: str, client_id: str) -> tuple[PresentationExportRecord, ...]:
        directory = self._directory(workspace_id, client_id)
        if not directory.exists():
            return ()
        records = [
            PresentationExportRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(directory.glob("*.json"))
        ]
        return tuple(sorted(records, key=lambda item: item.version))

    def get(self, workspace_id: str, client_id: str, export_id: str) -> PresentationExportRecord:
        _safe_identifier(export_id, "export_id")
        for record in self.list(workspace_id, client_id):
            if record.export_id == export_id:
                return record
        raise KeyError(f"presentation export not found: {export_id}")

    def save(self, record: PresentationExportRecord) -> None:
        directory = self._directory(record.workspace_id, record.client_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record.version:06d}-{record.export_id}.json"
        if path.exists():
            raise ValueError("presentation export records are immutable")
        fd, temporary = tempfile.mkstemp(prefix=".export-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record.to_dict(), handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class BlueprintPresentationExporter:
    def __init__(self, adapter: PresentationAdapter, store: FilePresentationExportStore) -> None:
        self.adapter = adapter
        self.store = store

    def export(
        self,
        request: PresentationExportRequest,
        renderable_blueprint: Mapping[str, Any],
    ) -> PresentationExportRecord:
        self._validate_renderable(request, renderable_blueprint)
        request_checksum = _checksum(request.identity_payload())
        existing = self.store.list(request.workspace_id, request.client_id)
        if request.requested_version is None:
            for record in existing:
                if record.request_checksum == request_checksum and record.status == "completed":
                    return record
        version = request.requested_version or (max((record.version for record in existing), default=0) + 1)
        export_id = f"{request.blueprint_id}-slides-v{version}"
        try:
            result = self.adapter.export(request=request, renderable_blueprint=renderable_blueprint)
        except Exception as exc:
            record = PresentationExportRecord(
                export_id=export_id,
                version=version,
                workspace_id=request.workspace_id,
                client_id=request.client_id,
                status="failed",
                request_checksum=request_checksum,
                source_blueprint_id=request.blueprint_id,
                source_blueprint_version=request.blueprint_version,
                renderable_checksum=request.renderable_checksum,
                canon_version=request.canon_version,
                canon_checksums=dict(request.canon_checksums),
                template_id=request.template.template_id,
                template_version=request.template.template_version,
                destination_folder_id=request.template.destination_folder_id,
                retryable=bool(getattr(exc, "retryable", False)),
                error_code=exc.__class__.__name__,
                error_message=str(exc)[:500],
            )
            self.store.save(record)
            return record
        record = PresentationExportRecord(
            export_id=export_id,
            version=version,
            workspace_id=request.workspace_id,
            client_id=request.client_id,
            status="completed",
            request_checksum=request_checksum,
            source_blueprint_id=request.blueprint_id,
            source_blueprint_version=request.blueprint_version,
            renderable_checksum=request.renderable_checksum,
            canon_version=request.canon_version,
            canon_checksums=dict(request.canon_checksums),
            template_id=request.template.template_id,
            template_version=request.template.template_version,
            destination_folder_id=request.template.destination_folder_id,
            presentation_id=result.presentation_id,
            presentation_url=result.presentation_url,
            provider=result.provider,
            provider_request_id=result.provider_request_id,
            completed_at=_utc_now(),
        )
        self.store.save(record)
        return record

    @staticmethod
    def _validate_renderable(
        request: PresentationExportRequest,
        renderable_blueprint: Mapping[str, Any],
    ) -> None:
        if not isinstance(renderable_blueprint, Mapping):
            raise ValueError("renderable_blueprint must be an object")
        workspace_id = str(renderable_blueprint.get("workspace_id", "")).strip()
        client_id = str(renderable_blueprint.get("client_id", "")).strip()
        if workspace_id and workspace_id != request.workspace_id:
            raise ValueError("renderable Blueprint belongs to a different workspace")
        if client_id and client_id != request.client_id:
            raise ValueError("renderable Blueprint belongs to a different client")
        slides = renderable_blueprint.get("slides")
        if not isinstance(slides, list) or len(slides) != 30:
            raise ValueError("renderable Blueprint must contain exactly 30 slides")
        slide_numbers = [int(slide.get("slide_no", 0)) for slide in slides if isinstance(slide, Mapping)]
        if slide_numbers != list(range(1, 31)):
            raise ValueError("renderable Blueprint slide ordering must be deterministic from 1 to 30")
        actual_checksum = _checksum(dict(renderable_blueprint))
        if actual_checksum != request.renderable_checksum:
            raise ValueError("renderable Blueprint checksum does not match export request")
