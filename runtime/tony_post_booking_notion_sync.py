from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyPostBookingNotionSyncCommandService:
    """Synchronise a verified Calendar booking into authoritative commercial state."""

    APPROVALS = {"do that", "do it", "go ahead", "update notion", "record it", "yes do that", "yes, do that"}

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
        pending = self.state.get("pending")
        if isinstance(pending, dict) and normalized in self.APPROVALS:
            return self._sync(pending)
        response = self.command_service.execute(command, objects)
        return self._prepare(response)

    def _prepare(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        booking = data.get("calendar_booking") if isinstance(data.get("calendar_booking"), dict) else {}
        if data.get("execution_status") != "discovery_booking_verified" or booking.get("state") != "verified":
            return response
        event_id = str(booking.get("event_id") or "").strip()
        if not event_id:
            return response
        completed = set(self.state.get("completed", []))
        existing = self.state.get("pending") if isinstance(self.state.get("pending"), dict) else {}
        if event_id in completed or existing.get("calendar_event_id") == event_id:
            return response
        pending = {
            "calendar_event_id": event_id,
            "lead_id": str(booking.get("lead_id") or ""),
            "contact": str(booking.get("contact") or ""),
            "company": str(booking.get("company") or ""),
            "slot": dict(booking.get("slot") or {}) if isinstance(booking.get("slot"), dict) else {},
        }
        self.state["pending"] = pending
        self._persist()
        data["execution_status"] = "calendar_verified_notion_approval_required"
        data["commercial_state_sync"] = {"state": "awaiting_approval", "worker": "Notion", "status": "Discovery booked", "approval_required": True, **pending}
        label = pending["contact"] or pending["lead_id"] or "the lead"
        return CommandResponse(response.command, response.status, response.message + f" I have prepared the Notion update to move {label} to Discovery booked against Calendar event {event_id}, but have not changed the record. Say 'do that' to approve it.", data)

    def _sync(self, pending: dict[str, Any]) -> CommandResponse:
        handler = self.dispatchers.get("Notion")
        if handler is None:
            return CommandResponse("post_booking_notion_sync", "healthy", "The meeting is verified in Calendar, but no live Notion dispatcher is configured. The stage update remains pending.", {"execution_status": "notion_dispatcher_unavailable", "external_action_taken": False})
        dispatch = {
            "worker": "Notion", "state": "approved_pending_execution", "execution_mode": "approval_gated_write",
            "approval_granted": True, "approval_scope": "verified_discovery_booking_state_sync", "execution_truth": "not_dispatched",
            "target": {"lead_id": pending.get("lead_id", ""), "contact": pending.get("contact", ""), "company": pending.get("company", ""), "area": "commercial"},
            "payload": {"kind": "confirmed_discovery_booking_state_update", "status": "Discovery booked", **pending},
            "instruction": "Update the authoritative lead to Discovery booked, preserving the verified Calendar event identifier and slot.",
            "expected_evidence": "verified Notion update with record identifier", "return_to": "Tony",
        }
        try:
            evidence = handler(dict(dispatch))
        except Exception as exc:
            return CommandResponse("post_booking_notion_sync", "healthy", f"The approved Notion update failed: {exc}. It remains pending.", {"execution_status": "notion_sync_failed", "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        notion_id = str(evidence.get("page_id") or evidence.get("record_id") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not notion_id:
            return CommandResponse("post_booking_notion_sync", "healthy", f"The Notion evidence was insufficient ({reason if not verified else 'missing record identifier'}). The update remains pending.", {"execution_status": "notion_sync_unverified", "external_action_taken": False})
        event_id = str(pending.get("calendar_event_id") or "")
        completed = list(self.state.get("completed", []))
        if event_id not in completed:
            completed.append(event_id)
        self.state = {"pending": None, "completed": completed[-100:]}
        self._persist()
        return CommandResponse(
            "post_booking_notion_sync",
            "healthy",
            f"Confirmed. Notion is now Discovery booked against Calendar event {event_id} and record {notion_id}.",
            {
                "execution_status": "discovery_commercial_state_sync_verified",
                "calendar_event_id": event_id,
                "notion_receipt": notion_id,
                "notion_evidence": dict(evidence),
                "discovery_tracking": dict(pending),
                "external_action_taken": True,
            },
        )

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed": []}
        return value if isinstance(value, dict) else {"pending": None, "completed": []}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)
