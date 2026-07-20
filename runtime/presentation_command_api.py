from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from .command_api import CommandError
from .presentation_export import (
    BlueprintPresentationExporter,
    PresentationExportRequest,
    PresentationTemplateConfiguration,
)


class CommandHandler(Protocol):
    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]: ...


class PresentationExportCommandAPI:
    """Adds export commands without coupling the core command API to Google or Claude.

    The delegate remains the existing authenticated workspace command API. Deployments
    wrap it with this boundary and inject workspace-scoped exporters and RenderableBlueprint
    loaders. This keeps Claude/Google details outside the runtime command implementation.
    """

    def __init__(
        self,
        delegate: CommandHandler,
        exporter_for_workspace: Callable[[str], BlueprintPresentationExporter],
        renderable_loader: Callable[[str, str, str, int], Mapping[str, Any]],
    ) -> None:
        self.delegate = delegate
        self.exporter_for_workspace = exporter_for_workspace
        self.renderable_loader = renderable_loader

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        command = str(request.get("command", "")).strip()
        if command not in {"blueprints.export", "blueprint-exports.get", "blueprint-exports.list"}:
            return self.delegate.handle(request)
        workspace_id = self._required(request, "workspace_id")
        client_id = self._required(request, "client_id")
        nested = request.get("request")
        if nested is not None:
            if not isinstance(nested, Mapping):
                raise CommandError("invalid_export_request", "request must be an object")
            self._reject_nested_mismatch(nested, workspace_id, client_id)
        exporter = self.exporter_for_workspace(workspace_id)
        if command == "blueprints.export":
            payload = dict(nested or request)
            blueprint_id = self._required(payload, "blueprint_id")
            blueprint_version = self._positive_int(payload, "blueprint_version")
            renderable = self.renderable_loader(
                workspace_id, client_id, blueprint_id, blueprint_version
            )
            template = PresentationTemplateConfiguration(
                template_id=self._required(payload, "template_id"),
                template_version=self._required(payload, "template_version"),
                destination_folder_id=self._required(payload, "destination_folder_id"),
            )
            export_request = PresentationExportRequest(
                workspace_id=workspace_id,
                client_id=client_id,
                blueprint_id=blueprint_id,
                blueprint_version=blueprint_version,
                renderable_checksum=self._required(payload, "renderable_checksum"),
                canon_version=self._required(payload, "canon_version"),
                canon_checksums=dict(payload.get("canon_checksums", {}) or {}),
                template=template,
                requested_version=(
                    int(payload["requested_version"])
                    if payload.get("requested_version") is not None
                    else None
                ),
            )
            record = exporter.export(export_request, renderable)
            return {"ok": True, "command": command, "workspace_id": workspace_id, "data": record.to_dict()}
        if command == "blueprint-exports.get":
            export_id = self._required(request, "export_id")
            try:
                record = exporter.store.get(workspace_id, client_id, export_id)
            except KeyError as exc:
                raise CommandError("presentation_export_not_found", str(exc), 404) from exc
            return {"ok": True, "command": command, "workspace_id": workspace_id, "data": record.to_dict()}
        records = [record.to_dict() for record in exporter.store.list(workspace_id, client_id)]
        return {
            "ok": True,
            "command": command,
            "workspace_id": workspace_id,
            "data": {"exports": records, "count": len(records)},
        }

    @staticmethod
    def _reject_nested_mismatch(
        payload: Mapping[str, Any], workspace_id: str, client_id: str
    ) -> None:
        nested_workspace = str(payload.get("workspace_id", "")).strip()
        nested_client = str(payload.get("client_id", "")).strip()
        if nested_workspace and nested_workspace != workspace_id:
            raise CommandError(
                "cross_workspace_reference",
                "export request workspace_id belongs to a different workspace",
                409,
            )
        if nested_client and nested_client != client_id:
            raise CommandError(
                "cross_workspace_reference",
                "export request client_id belongs to a different workspace",
                409,
            )

    @staticmethod
    def _required(request: Mapping[str, Any], field: str) -> str:
        value = str(request.get(field, "")).strip()
        if not value:
            raise CommandError("missing_field", f"{field} is required")
        return value

    @classmethod
    def _positive_int(cls, request: Mapping[str, Any], field: str) -> int:
        value = int(cls._required(request, field))
        if value <= 0:
            raise CommandError("invalid_field", f"{field} must be positive")
        return value
