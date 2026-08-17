from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyDriveDeliveryWorkspaceCommandService:
    """Create a client Drive workspace only after verified delivery bootstrap and scoped approval."""

    APPROVALS = {
        "create drive workspace",
        "create the drive workspace",
        "create client drive workspace",
        "create the client drive workspace",
        "set up drive workspace",
        "set up the drive workspace",
    }
    GENERIC_APPROVALS = {"do that", "go ahead", "ok", "okay", "yes", "yes do that"}

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
            return self._create(pending)
        if pending and normalized in self.GENERIC_APPROVALS:
            return self._ready(pending, generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "delivery_bootstrap_verified":
            return response
        delivery = data.get("delivery_bootstrap") if isinstance(data.get("delivery_bootstrap"), dict) else {}
        project_id = str(delivery.get("delivery_project_record_id") or "").strip()
        if not project_id:
            return response
        completed = set(str(item) for item in self.state.get("completed", []) if item)
        if project_id in completed:
            return response
        pending = {
            "delivery_project_record_id": project_id,
            "onboarding_record_id": str(delivery.get("onboarding_record_id") or ""),
            "lead_id": str(delivery.get("lead_id") or ""),
            "contact": str(delivery.get("contact") or ""),
            "company": str(delivery.get("company") or ""),
        }
        self.state["pending"] = pending
        self._persist()
        return self._ready(pending, prefix=response.message + " ")

    def _ready(self, pending: dict[str, Any], *, generic: bool = False, prefix: str = "") -> CommandResponse:
        label = str(pending.get("company") or pending.get("contact") or "the client")
        warning = "A generic approval is not enough to create an external client workspace. " if generic else ""
        message = prefix + warning + f"{label}'s verified delivery project is ready for its Google Drive workspace. Say 'create Drive workspace' to approve that external workspace creation. This does not send client email, schedule meetings or commission delivery work."
        return CommandResponse("drive_delivery_workspace", "healthy", message, {"execution_status": "drive_workspace_approval_required", "drive_workspace": {**pending, "state": "ready", "approval_required": True, "workspace_created": False}, "external_action_taken": False})

    def _create(self, pending: dict[str, Any]) -> CommandResponse:
        drive = self.dispatchers.get("Google Drive")
        if drive is None:
            return CommandResponse("drive_delivery_workspace", "healthy", "Drive workspace approval is recorded, but no live Google Drive dispatcher is configured. I have not created any folders.", {"execution_status": "drive_workspace_dispatcher_unavailable", "drive_workspace": {**pending, "state": "approved_pending_execution", "workspace_created": False}, "external_action_taken": False})
        dispatch = {
            "worker": "Google Drive",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_delivery_project_drive_workspace",
            "execution_truth": "not_dispatched",
            "target": {"lead_id": pending.get("lead_id", ""), "contact": pending.get("contact", ""), "company": pending.get("company", ""), "delivery_project_record_id": pending.get("delivery_project_record_id", ""), "area": "delivery"},
            "payload": {"kind": "client_delivery_drive_workspace", "delivery_project_record_id": pending.get("delivery_project_record_id", ""), "folder_structure": ["01 Strategy", "02 Research", "03 Creative", "04 Client Deliverables", "05 Reporting"]},
            "instruction": "Create one client delivery workspace in Google Drive linked to the verified delivery project, with the requested standard folders. Do not send email, create calendar events, share externally, or commission delivery work in this step.",
            "expected_evidence": "verified Google Drive mutation with root folder identifier and folder URL",
            "return_to": "Tony",
        }
        try:
            evidence = drive(dict(dispatch))
        except Exception as exc:
            return CommandResponse("drive_delivery_workspace", "healthy", f"The approved Drive workspace creation failed: {exc}. I have not treated any workspace as created.", {"execution_status": "drive_workspace_write_failed", "drive_workspace": {**pending, "workspace_created": False}, "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        folder_id = str(evidence.get("folder_id") or evidence.get("root_folder_id") or evidence.get("file_id") or "").strip() if isinstance(evidence, dict) else ""
        folder_url = str(evidence.get("folder_url") or evidence.get("web_view_link") or evidence.get("url") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not folder_id or not folder_url:
            detail = reason if not verified else "missing Drive root folder identifier or folder URL"
            return CommandResponse("drive_delivery_workspace", "healthy", f"The Drive workspace evidence was insufficient ({detail}). I am not treating the workspace as created.", {"execution_status": "drive_workspace_write_unverified", "drive_workspace": {**pending, "workspace_created": False}, "drive_evidence": dict(evidence) if isinstance(evidence, dict) else {}, "external_action_taken": False})
        completed = [str(item) for item in self.state.get("completed", []) if item]
        project_id = str(pending.get("delivery_project_record_id") or "")
        if project_id and project_id not in completed:
            completed.append(project_id)
        self.state = {"pending": None, "completed": completed[-100:], "workspace": {**pending, "state": "created_verified", "workspace_created": True, "drive_folder_id": folder_id, "drive_folder_url": folder_url}}
        self._persist()
        return CommandResponse("drive_delivery_workspace", "healthy", f"Google Drive workspace creation is verified for {pending.get('company') or pending.get('contact') or 'the client'}. I have not shared it externally, sent client communications, scheduled meetings or commissioned delivery work.", {"execution_status": "drive_workspace_verified", "drive_workspace": dict(self.state["workspace"]), "drive_evidence": dict(evidence), "external_action_taken": True})

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed": []}
        return value if isinstance(value, dict) else {"pending": None, "completed": []}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.store_path)
