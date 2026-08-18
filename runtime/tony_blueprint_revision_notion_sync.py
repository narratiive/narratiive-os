from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintRevisionNotionSyncCommandService:
    """Record verified Blueprint revision redelivery in authoritative Notion state.

    Drive redelivery proves only that the exact revised artifact became client-accessible.
    This layer keeps that evidence separate from authoritative delivery state and requires
    a fresh scoped approval before Notion is mutated. It never infers acknowledgement,
    acceptance or project completion from the share action.
    """

    APPROVALS = {
        "record growth blueprint revision delivery",
        "record blueprint revision delivery",
        "update notion with growth blueprint revision delivery",
        "mark growth blueprint revision delivered in notion",
        "mark the growth blueprint revision delivered in notion",
    }
    GENERIC_APPROVALS = {"do that", "go ahead", "ok", "okay", "yes", "yes do that", "approve it"}
    AUTHORITATIVE_STATUS = "Growth Blueprint revision delivered"

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
            return self._sync(pending)
        if pending and normalized in self.GENERIC_APPROVALS:
            return self._ready(pending, generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "blueprint_revision_client_delivery_verified":
            return response
        delivery = data.get("blueprint_revision_delivery") if isinstance(data.get("blueprint_revision_delivery"), dict) else {}
        project_id = str(delivery.get("delivery_project_record_id") or "").strip()
        revision_file_id = str(delivery.get("revision_file_id") or "").strip()
        original_file_id = str(delivery.get("original_delivered_file_id") or delivery.get("growth_blueprint_file_id") or "").strip()
        delivery_url = str(delivery.get("delivery_url") or "").strip()
        if not project_id or not revision_file_id or not delivery_url:
            return response
        key = self._key(project_id, revision_file_id)
        completed = set(str(item) for item in self.state.get("completed", []) if item)
        if key in completed:
            return response
        pending = {
            "delivery_project_record_id": project_id,
            "lead_id": str(delivery.get("lead_id") or ""),
            "contact": str(delivery.get("contact") or ""),
            "company": str(delivery.get("company") or ""),
            "revision_file_id": revision_file_id,
            "revision_file_url": str(delivery.get("revision_file_url") or ""),
            "original_delivered_file_id": original_file_id,
            "delivery_url": delivery_url,
            "feedback_message_id": str(delivery.get("feedback_message_id") or ""),
        }
        self.state["pending"] = pending
        self._persist()
        return self._ready(pending, prefix=response.message + " ")

    def _ready(self, pending: dict[str, Any], *, generic: bool = False, prefix: str = "") -> CommandResponse:
        label = str(pending.get("company") or pending.get("contact") or "the client")
        warning = "A generic approval is not enough to change the authoritative revision-delivery record. " if generic else ""
        return CommandResponse(
            "blueprint_revision_notion_sync",
            "healthy",
            prefix + warning + f"The verified Growth Blueprint revision delivery for {label} is ready to be recorded in Notion. Say 'record Growth Blueprint revision delivery' to approve this exact state update. This records verified redelivery only; client acknowledgement and acceptance remain unverified.",
            {
                "execution_status": "blueprint_revision_notion_sync_approval_required",
                "blueprint_revision_delivery_state": {**pending, "status": "awaiting_scoped_approval"},
                "approval_required": True,
                "external_action_taken": False,
            },
        )

    def _sync(self, pending: dict[str, Any]) -> CommandResponse:
        notion = self.dispatchers.get("Notion")
        if notion is None:
            return CommandResponse(
                "blueprint_revision_notion_sync",
                "healthy",
                "The Blueprint revision redelivery is verified and the Notion update is approved, but no live Notion dispatcher is configured. The authoritative record has not been changed.",
                {"execution_status": "blueprint_revision_notion_dispatcher_unavailable", "blueprint_revision_delivery_state": dict(pending), "external_action_taken": False},
            )
        dispatch = {
            "worker": "Notion",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_growth_blueprint_revision_delivery_state_sync",
            "execution_truth": "not_dispatched",
            "target": {
                "delivery_project_record_id": pending["delivery_project_record_id"],
                "lead_id": pending.get("lead_id", ""),
                "contact": pending.get("contact", ""),
                "company": pending.get("company", ""),
                "area": "delivery",
            },
            "payload": {
                "kind": "growth_blueprint_revision_delivery_state_update",
                "delivery_project_record_id": pending["delivery_project_record_id"],
                "revision_file_id": pending["revision_file_id"],
                "original_delivered_file_id": pending.get("original_delivered_file_id", ""),
                "delivery_url": pending["delivery_url"],
                "feedback_message_id": pending.get("feedback_message_id", ""),
                "status": self.AUTHORITATIVE_STATUS,
            },
            "instruction": "Update only the authoritative Notion delivery record to show that the exact verified Growth Blueprint revision artifact was redelivered. Preserve both the new revision file identifier and the prior delivered file identifier as evidence. Do not infer client receipt, acknowledgement, acceptance, satisfaction or project completion, and do not create any other client, calendar, email or delivery state.",
            "expected_evidence": "verified Notion mutation with record/page identifier and returned Growth Blueprint revision delivered status",
            "return_to": "Tony",
        }
        try:
            evidence = notion(dict(dispatch))
        except Exception as exc:
            return CommandResponse(
                "blueprint_revision_notion_sync",
                "healthy",
                f"I attempted the approved Notion revision-delivery update, but it failed: {exc}. The authoritative record remains unverified.",
                {"execution_status": "blueprint_revision_notion_sync_failed", "blueprint_revision_delivery_state": dict(pending), "external_action_taken": False},
            )
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        notion_id = str(evidence.get("record_id") or evidence.get("page_id") or "").strip() if isinstance(evidence, dict) else ""
        returned_status = str(evidence.get("status") or evidence.get("delivery_status") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not notion_id or returned_status.casefold() != self.AUTHORITATIVE_STATUS.casefold():
            detail = reason if not verified else "missing authoritative record id or exact returned revision-delivery status"
            return CommandResponse(
                "blueprint_revision_notion_sync",
                "healthy",
                f"The Notion revision-delivery evidence was insufficient ({detail}). Tony is not treating the authoritative record as updated.",
                {
                    "execution_status": "blueprint_revision_notion_sync_unverified",
                    "blueprint_revision_delivery_state": dict(pending),
                    "notion_evidence": dict(evidence) if isinstance(evidence, dict) else {},
                    "external_action_taken": False,
                },
            )
        key = self._key(pending["delivery_project_record_id"], pending["revision_file_id"])
        completed = [str(item) for item in self.state.get("completed", []) if item]
        if key not in completed:
            completed.append(key)
        result = {**pending, "status": self.AUTHORITATIVE_STATUS, "notion_record_id": notion_id}
        self.state = {"pending": None, "completed": completed[-100:], "last_completed": result}
        self._persist()
        return CommandResponse(
            "blueprint_revision_notion_sync",
            "healthy",
            f"Confirmed. The authoritative Notion delivery record now shows {self.AUTHORITATIVE_STATUS} for {pending.get('company') or pending.get('contact') or 'the client'}. This records verified revision redelivery only; client acknowledgement and acceptance remain unverified until separate evidence exists.",
            {
                "execution_status": "blueprint_revision_notion_sync_verified",
                "blueprint_revision_delivery_state": result,
                "notion_record_id": notion_id,
                "notion_evidence": dict(evidence),
                "external_action_taken": True,
            },
        )

    @staticmethod
    def _key(project_id: str, file_id: str) -> str:
        return f"{project_id}:{file_id}"

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed": []}
        if not isinstance(value, dict):
            return {"pending": None, "completed": []}
        value.setdefault("completed", [])
        return value

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.store_path)
