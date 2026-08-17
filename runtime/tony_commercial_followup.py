from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from runtime.tony_command_service import CommandResponse


class TonyCommercialFollowupCommandService:
    """Turn a verified Contacted state into safe reply/follow-up monitoring.

    Monitoring is read-only: Tony may ask Gmail for thread evidence without approval.
    A follow-up send is never performed here; after three business days with no reply,
    Tony only prepares the bounded next step for the existing review/approval pipeline.
    """

    def __init__(self, command_service, *, clock: Callable[[], datetime] | None = None) -> None:
        self.command_service = command_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        response = self.command_service.execute(command, objects)
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "commercial_state_sync_verified":
            return response
        message_id = str(data.get("gmail_message_id") or "").strip()
        if not message_id:
            return response

        target = data.get("commercial_state_sync") if isinstance(data.get("commercial_state_sync"), dict) else {}
        sent_at = self._now()
        due = self._add_business_days(sent_at, 3)
        handoff = {
            "worker": "Gmail",
            "approval_required": False,
            "execution_mode": "autonomous_read",
            "action": "Monitor the verified outbound Gmail thread for a genuine lead reply.",
            "dispatch": {
                "eligible": True,
                "state": "ready_for_autonomous_dispatch",
                "worker": "Gmail",
                "instruction": (
                    f"Read the Gmail thread anchored by outbound message {message_id}. Return only new inbound reply evidence, "
                    "including sender, received time, body/snippet and thread/message identifiers. Do not send, label, archive or mutate Gmail."
                ),
                "target": {
                    "lead_id": str(target.get("lead_id") or ""),
                    "contact": str(target.get("contact") or ""),
                    "area": "commercial",
                },
                "execution_mode": "autonomous_read",
                "expected_evidence": "verified Gmail thread read with message/thread identifiers",
                "return_to": "Tony",
                "execution_truth": "not_dispatched",
                "payload": {"kind": "commercial_reply_monitor", "gmail_message_id": message_id},
            },
        }
        data["reply_monitor"] = {
            "status": "active",
            "gmail_message_id": message_id,
            "follow_up_due_at": due.isoformat(),
            "follow_up_after_business_days": 3,
            "external_action_taken": False,
        }
        data["execution_handoff"] = handoff
        data["execution_status"] = "reply_monitor_ready"
        return CommandResponse(
            response.command,
            response.status,
            response.message
            + f" I will now monitor the verified Gmail thread read-only. If there is no genuine reply by {due.date().isoformat()}, the next step is to prepare a follow-up for review; nothing will be sent without the existing approval gate.",
            data,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _add_business_days(value: datetime, days: int) -> datetime:
        current = value
        remaining = days
        while remaining:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current
