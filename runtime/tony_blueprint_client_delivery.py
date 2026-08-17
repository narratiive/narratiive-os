from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintClientDeliveryCommandService:
    """Share a verified persisted Growth Blueprint only after explicit client-delivery approval."""

    APPROVALS = {
        "deliver growth blueprint",
        "deliver the growth blueprint",
        "share growth blueprint with client",
        "share the growth blueprint with client",
        "send growth blueprint to client",
        "send the growth blueprint to client",
    }
    GENERIC_APPROVALS = {"do that", "go ahead", "ok", "okay", "yes", "yes do that", "approve it"}

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending = self.state.get("pending") if isinstance(self.state.get("pending"), dict) else None
        if pending and normalized in self.APPROVALS:
            return self._deliver(pending)
        if pending and normalized in self.GENERIC_APPROVALS:
            return self._ready(pending, generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "delivery_blueprint_persisted_verified":
            return response
        blueprint = data.get("delivery_blueprint") if isinstance(data.get("delivery_blueprint"), dict) else {}
        file_id = str(blueprint.get("growth_blueprint_file_id") or "").strip()
        file_url = str(blueprint.get("growth_blueprint_file_url") or "").strip()
        project_id = str(blueprint.get("delivery_project_record_id") or "").strip()
        if not file_id or not file_url or not project_id:
            return response
        delivered = set(str(item) for item in self.state.get("delivered", []) if item)
        if project_id in delivered:
            return response
        pending = {
            "delivery_project_record_id": project_id,
            "lead_id": str(blueprint.get("lead_id") or ""),
            "contact": str(blueprint.get("contact") or ""),
            "company": str(blueprint.get("company") or ""),
            "growth_blueprint_file_id": file_id,
            "growth_blueprint_file_url": file_url,
            "growth_blueprint_filename": str(blueprint.get("growth_blueprint_filename") or "Growth Blueprint"),
        }
        self.state["pending"] = pending
        self._persist()
        return self._ready(pending, prefix=response.message + " ")

    def _ready(self, pending: dict[str, Any], *, generic: bool = False, prefix: str = "") -> CommandResponse:
        label = str(pending.get("company") or pending.get("contact") or "the client")
        warning = "A generic approval is not enough to expose a client-facing artifact. " if generic else ""
        return CommandResponse(
            "blueprint_client_delivery",
            "healthy",
            prefix + warning + f"The verified Growth Blueprint for {label} is ready for client delivery. Say 'deliver Growth Blueprint' to approve sharing this exact verified Drive artifact with the client. This approval does not create meetings or change Notion commercial state.",
            {"execution_status": "blueprint_client_delivery_approval_required", "blueprint_delivery": {**pending, "state": "awaiting_scoped_approval"}, "approval_required": True, "external_action_taken": False},
        )

    def _deliver(self, pending: dict[str, Any]) -> CommandResponse:
        drive = self.dispatchers.get("Google Drive")
        label = str(pending.get("company") or pending.get("contact") or "the client")
        if drive is None:
            return CommandResponse("blueprint_client_delivery", "healthy", "Client delivery is approved, but no live Google Drive dispatcher is configured. The Growth Blueprint has not been shared.", {"execution_status": "blueprint_client_delivery_dispatcher_unavailable", "external_action_taken": False})
        dispatch = {
            "worker": "Google Drive",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_growth_blueprint_client_delivery",
            "execution_truth": "not_dispatched",
            "target": {"delivery_project_record_id": pending.get("delivery_project_record_id", ""), "company": pending.get("company", ""), "contact": pending.get("contact", ""), "area": "delivery"},
            "payload": {"kind": "share_verified_growth_blueprint", "file_id": pending["growth_blueprint_file_id"], "file_url": pending["growth_blueprint_file_url"], "filename": pending["growth_blueprint_filename"]},
            "instruction": "Make the exact verified Growth Blueprint artifact client-deliverable using the configured bounded Drive delivery action. Do not alter its content, create calendar events, update Notion, or commission further work. Return explicit evidence that this exact file became externally accessible through the approved delivery action.",
            "expected_evidence": "verified Google Drive mutation proving the exact Growth Blueprint file was made client-deliverable, with file identifier and delivery/share URL",
            "return_to": "Tony",
        }
        try:
            evidence = drive(dict(dispatch))
        except Exception as exc:
            return CommandResponse("blueprint_client_delivery", "healthy", f"The approved Growth Blueprint delivery failed: {exc}. Tony is not treating it as delivered.", {"execution_status": "blueprint_client_delivery_failed", "external_action_taken": False})

        # The shared dispatcher contract recognises `url` as a canonical write-result
        # identifier. Drive delivery adapters commonly return the more specific
        # `share_url`/`delivery_url`; map that returned evidence into the canonical
        # verifier shape without inventing any execution evidence.
        verification_evidence: Any = evidence
        if isinstance(evidence, dict):
            verification_evidence = dict(evidence)
            if not str(verification_evidence.get("url") or "").strip():
                returned_url = str(verification_evidence.get("delivery_url") or verification_evidence.get("share_url") or "").strip()
                if returned_url:
                    verification_evidence["url"] = returned_url

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, verification_evidence)
        file_id = str(evidence.get("file_id") or evidence.get("document_id") or "").strip() if isinstance(evidence, dict) else ""
        delivery_url = str(evidence.get("delivery_url") or evidence.get("share_url") or evidence.get("url") or "").strip() if isinstance(evidence, dict) else ""
        externally_accessible = bool(evidence.get("externally_accessible") or evidence.get("shared")) if isinstance(evidence, dict) else False
        if not verified or file_id != pending["growth_blueprint_file_id"] or not delivery_url or not externally_accessible:
            detail = reason if not verified else "missing exact-file client delivery proof"
            return CommandResponse("blueprint_client_delivery", "healthy", f"The Growth Blueprint delivery evidence was insufficient ({detail}). Tony is not treating the artifact as delivered.", {"execution_status": "blueprint_client_delivery_unverified", "drive_evidence": dict(evidence) if isinstance(evidence, dict) else {}, "external_action_taken": False})
        project_id = str(pending.get("delivery_project_record_id") or "")
        delivered = [str(item) for item in self.state.get("delivered", []) if item]
        if project_id and project_id not in delivered:
            delivered.append(project_id)
        result = {**pending, "state": "client_delivery_verified", "delivery_url": delivery_url}
        self.state = {"pending": None, "delivered": delivered[-100:], "last_delivered": result}
        self._persist()
        return CommandResponse("blueprint_client_delivery", "healthy", f"Client delivery of the verified Growth Blueprint for {label} is now evidenced. Tony has not inferred client receipt, acknowledgement or acceptance from the share action itself.", {"execution_status": "blueprint_client_delivery_verified", "blueprint_delivery": result, "drive_evidence": dict(evidence), "external_action_taken": True})

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "delivered": []}
        if not isinstance(value, dict):
            return {"pending": None, "delivered": []}
        value.setdefault("delivered", [])
        return value

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.store_path)
