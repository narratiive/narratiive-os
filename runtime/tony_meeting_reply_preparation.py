from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TonyMeetingReplyPreparationCommandService:
    """Progress a verified meeting-intent reply through safe Calendar and Claude work.

    Calendar availability is read-only and may run autonomously. Claude may then prepare
    a discovery reply grounded only in the verified slots. Neither stage may send mail,
    create a Calendar event, or mutate commercial state.
    """

    def __init__(self, command_service, dispatchers: Mapping[str, DispatchHandler] | None = None) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        response = self.command_service.execute(command, objects)
        data = dict(response.data) if isinstance(response.data, dict) else {}
        handoff = data.get("execution_handoff") if isinstance(data.get("execution_handoff"), dict) else {}
        dispatch = handoff.get("dispatch") if isinstance(handoff.get("dispatch"), dict) else {}
        if not self._is_calendar_meeting_handoff(dispatch):
            return response

        calendar = self.dispatchers.get("Google Calendar")
        if calendar is None:
            return self._blocked(response, data, "calendar_dispatcher_unavailable", "no live Google Calendar read dispatcher is configured")
        try:
            availability = calendar(dict(dispatch))
        except Exception as exc:
            return self._blocked(response, data, "calendar_availability_failed", f"the Calendar read failed: {exc}")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, availability)
        if not verified:
            return self._blocked(response, data, "calendar_availability_unverified", f"Calendar evidence was not decision-grade ({reason})")

        rendered = self._availability_text(availability)
        if not rendered:
            return self._blocked(response, data, "calendar_availability_unverified", "Calendar returned no usable availability")

        target = dispatch.get("target") if isinstance(dispatch.get("target"), dict) else {}
        contact = str(target.get("contact") or "the lead").strip() or "the lead"
        claude_dispatch = {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Claude",
            "instruction": (
                f"Prepare a concise discovery reply to {contact} using only this verified Calendar availability: {rendered}. "
                "Offer exactly two suitable times from the verified evidence. Do not invent or extend a slot. "
                "Do not send the email, create a Calendar event, update Notion, or change external state."
            ),
            "target": dict(target),
            "execution_mode": "autonomous_prepare",
            "expected_evidence": "verified prepared discovery reply grounded in Calendar availability",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "commercial_meeting_reply_prepare", "verified_availability": availability},
        }
        claude = self.dispatchers.get("Claude")
        if claude is None:
            data.update({
                "execution_status": "meeting_reply_preparation_dispatcher_unavailable",
                "calendar_availability_evidence": dict(availability),
                "execution_handoff": {"worker": "Claude", "approval_required": False, "execution_mode": "autonomous_prepare", "dispatch": claude_dispatch},
                "external_action_taken": False,
            })
            return CommandResponse(response.command, response.status, response.message + " Calendar availability is verified, but no live Claude dispatcher is configured to prepare the reply. Nothing has been sent or booked.", data)
        try:
            draft = claude(dict(claude_dispatch))
        except Exception as exc:
            return self._blocked(response, data, "meeting_reply_preparation_failed", f"Claude preparation failed: {exc}", availability=availability)
        draft_verified, draft_reason = TonyAutonomousDispatchCommandService._verify_evidence(claude_dispatch, draft)
        if not draft_verified:
            return self._blocked(response, data, "meeting_reply_preparation_unverified", f"Claude did not return a verified work product ({draft_reason})", availability=availability)

        data.update({
            "execution_status": "meeting_reply_draft_prepared",
            "calendar_availability_evidence": dict(availability),
            "meeting_reply_draft_evidence": dict(draft),
            "verified_availability_summary": rendered,
            "external_action_taken": False,
        })
        data.pop("execution_handoff", None)
        return CommandResponse(
            "commercial_meeting_reply",
            "healthy",
            response.message + " I verified Calendar availability and Claude has prepared a grounded discovery reply for Tony review. Nothing has been sent and no meeting has been booked.",
            data,
        )

    @staticmethod
    def _is_calendar_meeting_handoff(dispatch: dict[str, Any]) -> bool:
        worker = str(dispatch.get("worker") or "").strip().casefold()
        payload = dispatch.get("payload") if isinstance(dispatch.get("payload"), dict) else {}
        return worker in {"google calendar", "calendar"} and str(dispatch.get("execution_mode") or "") == "autonomous_read" and str(payload.get("kind") or "") == "commercial_calendar_availability"

    @staticmethod
    def _availability_text(evidence: dict[str, Any]) -> str:
        for key in ("availability", "available_slots", "slots", "options", "summary", "result"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
            if isinstance(value, (list, tuple)) and value:
                return "; ".join(str(item).strip() for item in value if str(item).strip())
        return ""

    @staticmethod
    def _blocked(response: CommandResponse, data: dict[str, Any], status: str, reason: str, *, availability: dict[str, Any] | None = None) -> CommandResponse:
        updated = dict(data)
        updated["execution_status"] = status
        updated["external_action_taken"] = False
        if availability is not None:
            updated["calendar_availability_evidence"] = dict(availability)
        return CommandResponse(response.command, response.status, response.message + f" I could not safely progress the meeting reply because {reason}. Nothing has been sent or booked.", updated)
