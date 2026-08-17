from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyDeliveryBootstrapCommandService:
    """Turn verified onboarding into a separately approved delivery workspace bootstrap."""

    APPROVALS = {
        "create delivery workspace",
        "create the delivery workspace",
        "bootstrap delivery",
        "start delivery setup",
        "set up delivery workspace",
        "set up the delivery workspace",
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
            return self._bootstrap(pending)
        if pending and normalized in self.GENERIC_APPROVALS:
            return self._ready(pending, generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "onboarding_started_verified":
            return response
        onboarding = data.get("onboarding") if isinstance(data.get("onboarding"), dict) else {}
        onboarding_record_id = str(onboarding.get("onboarding_record_id") or "").strip()
        if not onboarding_record_id:
            return response
        completed = set(str(item) for item in self.state.get("completed", []) if item)
        if onboarding_record_id in completed:
            return response
        pending = {
            "onboarding_record_id": onboarding_record_id,
            "opportunity_record_id": str(onboarding.get("opportunity_record_id") or ""),
            "lead_id": str(onboarding.get("lead_id") or ""),
            "contact": str(onboarding.get("contact") or ""),
            "company": str(onboarding.get("company") or ""),
        }
        self.state["pending"] = pending
        self._persist()
        return self._ready(pending, prefix=response.message + " ")

    def _ready(self, pending: dict[str, Any], *, generic: bool = False, prefix: str = "") -> CommandResponse:
        label = str(pending.get("company") or pending.get("contact") or "the client")
        warning = "A generic approval is not enough to create the delivery workspace. " if generic else ""
        message = prefix + warning + f"{label} has verified onboarding and is ready for delivery setup. Say 'create delivery workspace' to approve the authoritative Notion delivery-project record. This approval does not send client email, create calendar commitments, create Drive folders, or commission delivery work."
        return CommandResponse(
            "delivery_bootstrap",
            "healthy",
            message,
            {"execution_status": "delivery_bootstrap_approval_required", "delivery_bootstrap": {**pending, "state": "ready", "approval_required": True, "workspace_created": False}, "external_action_taken": False},
        )

    def _bootstrap(self, pending: dict[str, Any]) -> CommandResponse:
        notion = self.dispatchers.get("Notion")
        if notion is None:
            return CommandResponse("delivery_bootstrap", "healthy", "Delivery workspace approval is recorded, but no live Notion dispatcher is configured. I have not created a delivery project.", {"execution_status": "delivery_bootstrap_notion_dispatcher_unavailable", "delivery_bootstrap": {**pending, "state": "approved_pending_execution", "workspace_created": False}, "external_action_taken": False})
        dispatch = {
            "worker": "Notion",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_onboarding_delivery_bootstrap",
            "execution_truth": "not_dispatched",
            "target": {"lead_id": pending.get("lead_id", ""), "contact": pending.get("contact", ""), "company": pending.get("company", ""), "onboarding_record_id": pending.get("onboarding_record_id", ""), "area": "delivery"},
            "payload": {"kind": "client_delivery_project_bootstrap", "onboarding_record_id": pending.get("onboarding_record_id", ""), "source_opportunity_record_id": pending.get("opportunity_record_id", ""), "delivery_status": "Ready"},
            "instruction": "Create the authoritative client delivery project in Notion linked to the verified onboarding record and mark it Ready. Do not create Drive folders, send email, create calendar events, commission workers, or start delivery tasks in this step.",
            "expected_evidence": "verified Notion mutation with delivery project record identifier and Ready status",
            "return_to": "Tony",
        }
        try:
            evidence = notion(dict(dispatch))
        except Exception as exc:
            return CommandResponse("delivery_bootstrap", "healthy", f"The approved delivery bootstrap failed: {exc}. I have not treated a delivery project as created.", {"execution_status": "delivery_bootstrap_notion_write_failed", "delivery_bootstrap": {**pending, "workspace_created": False}, "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        record_id = str(evidence.get("page_id") or evidence.get("record_id") or evidence.get("project_record_id") or "").strip() if isinstance(evidence, dict) else ""
        returned_status = str(evidence.get("delivery_status") or evidence.get("status") or evidence.get("stage") or "").strip().casefold() if isinstance(evidence, dict) else ""
        if not verified or not record_id or returned_status not in {"ready", "delivery ready", "delivery_ready"}:
            detail = reason if not verified else "missing delivery project identifier or verified Ready status"
            return CommandResponse("delivery_bootstrap", "healthy", f"The delivery bootstrap evidence was insufficient ({detail}). I am not treating the delivery project as created.", {"execution_status": "delivery_bootstrap_notion_write_unverified", "delivery_bootstrap": {**pending, "workspace_created": False}, "notion_evidence": dict(evidence) if isinstance(evidence, dict) else {}, "external_action_taken": False})
        completed = [str(item) for item in self.state.get("completed", []) if item]
        onboarding_id = str(pending.get("onboarding_record_id") or "")
        if onboarding_id and onboarding_id not in completed:
            completed.append(onboarding_id)
        self.state = {"pending": None, "completed": completed[-100:], "delivery": {**pending, "state": "ready_verified", "workspace_created": True, "delivery_project_record_id": record_id}}
        self._persist()
        return CommandResponse("delivery_bootstrap", "healthy", f"Delivery bootstrap verified. Notion created the authoritative delivery project {record_id}, linked to onboarding. I have not sent client communications, created calendar commitments, created Drive folders or commissioned delivery work.", {"execution_status": "delivery_bootstrap_verified", "delivery_bootstrap": dict(self.state["delivery"]), "notion_evidence": dict(evidence), "external_action_taken": True})

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
