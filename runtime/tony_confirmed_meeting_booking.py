from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TonyConfirmedMeetingBookingCommandService:
    """Turn a recipient-confirmed proposed slot into an approval-gated Calendar event.

    The service captures the exact verified availability and reviewed meeting draft before
    the discovery reply is sent. Once Gmail proves that exact reply was sent, a read-only
    monitor checks the resulting thread for a recipient confirmation. Tony only prepares
    a booking when the reply maps unambiguously to one previously verified structured
    Calendar slot. Event creation remains a separate explicit approval gate and is only
    reported complete after Calendar returns mutation proof plus an event identifier.
    """

    _CHECK_MARKERS = {
        "check replies",
        "check reply",
        "check meeting reply",
        "has the lead replied",
        "has the client replied",
        "did they confirm",
        "have they confirmed",
    }
    _APPROVAL_MARKERS = {
        "book it",
        "book that",
        "book the meeting",
        "do that",
        "do it",
        "go ahead",
        "go ahead and book it",
        "yes book it",
        "yes, book it",
    }

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
    ) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self._state = self._load_state()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending = self._state.get("pending_booking")
        if isinstance(pending, dict) and normalized in self._APPROVAL_MARKERS:
            return self._execute_booking(pending)

        active = self._state.get("active_monitor")
        if isinstance(active, dict) and normalized in self._CHECK_MARKERS:
            return self._check_confirmation(active)

        response = self.command_service.execute(command, objects)
        self._capture_proposal(response)
        activated = self._activate_after_verified_send(response)
        return activated

    def _capture_proposal(self, response: CommandResponse) -> None:
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "meeting_reply_ready_for_approval":
            return
        availability = data.get("calendar_availability_evidence")
        draft_evidence = data.get("meeting_reply_draft_evidence")
        if not isinstance(availability, dict) or not isinstance(draft_evidence, dict):
            return
        slots = self._structured_slots(availability)
        if not slots:
            return
        monitor = data.get("reply_monitor") if isinstance(data.get("reply_monitor"), dict) else {}
        draft = self._first_text(draft_evidence, ("draft", "work_product", "content", "body", "result"))
        self._state["proposal"] = {
            "lead_id": str(monitor.get("lead_id") or ""),
            "contact": str(monitor.get("contact") or ""),
            "company": str(monitor.get("company") or ""),
            "reviewed_draft": draft,
            "available_slots": slots,
        }
        self._persist_state()

    def _activate_after_verified_send(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        result = data.get("dispatch_result") if isinstance(data.get("dispatch_result"), dict) else {}
        judgement = data.get("commercial_judgement") if isinstance(data.get("commercial_judgement"), dict) else {}
        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        if (
            data.get("execution_status") != "approved_step_verified"
            or str(result.get("worker") or "").strip().casefold() != "gmail"
            or str(result.get("status") or "").strip().casefold() != "verified"
            or judgement.get("disposition") != "meeting_draft_ready"
        ):
            return response
        message_id = str(evidence.get("message_id") or "").strip()
        proposal = self._state.get("proposal") if isinstance(self._state.get("proposal"), dict) else None
        if not message_id or not proposal:
            return response
        active = dict(proposal)
        active["gmail_message_id"] = message_id
        self._state["active_monitor"] = active
        self._state["pending_booking"] = None
        self._persist_state()
        data["meeting_confirmation_monitor"] = {
            "status": "active",
            "gmail_message_id": message_id,
            "contact": active.get("contact", ""),
            "approval_required_for_booking": True,
        }
        data["execution_status"] = "meeting_reply_sent_confirmation_monitor_active"
        return CommandResponse(
            response.command,
            response.status,
            response.message
            + " I will treat the meeting as unbooked until the recipient confirms one of the verified offered slots. Calendar creation still requires your approval.",
            data,
        )

    def _check_confirmation(self, active: dict[str, Any]) -> CommandResponse:
        gmail = self.dispatchers.get("Gmail")
        if gmail is None:
            return self._blocked(
                "meeting_confirmation_dispatcher_unavailable",
                "The discovery reply was sent, but no live Gmail read dispatcher is configured to verify a slot confirmation.",
                active,
            )
        dispatch = self._gmail_read_dispatch(active)
        try:
            evidence = gmail(dict(dispatch))
        except Exception as exc:
            return self._blocked(
                "meeting_confirmation_read_failed",
                f"I could not verify the recipient's confirmation because the Gmail read failed: {exc}",
                active,
            )
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return self._blocked(
                "meeting_confirmation_read_unverified",
                f"Gmail returned reply data, but it was not strong enough to use for a booking decision ({reason}).",
                active,
                evidence=evidence,
            )
        if evidence.get("reply_found") is False or not self._reply_text(evidence):
            return CommandResponse(
                "meeting_confirmation_monitor",
                "healthy",
                "I checked the verified Gmail thread. There is no confirmed meeting slot yet, so nothing has been booked.",
                {
                    "execution_status": "meeting_confirmation_monitor_active",
                    "meeting_confirmation_monitor": {"status": "active", **dict(active)},
                    "gmail_reply_evidence": dict(evidence),
                    "external_action_taken": False,
                },
            )

        matches = self._matching_slots(active, evidence)
        if len(matches) != 1:
            status = "meeting_confirmation_ambiguous" if matches else "meeting_confirmation_unmatched"
            explanation = (
                "The reply appears to mention more than one offered slot, so I will not guess which event to create."
                if matches
                else "The reply does not map exactly to one of the structured Calendar slots that were previously verified, so I will not invent a booking."
            )
            return self._blocked(status, explanation, active, evidence=evidence)

        slot = matches[0]
        pending = {
            "lead_id": str(active.get("lead_id") or ""),
            "contact": str(active.get("contact") or ""),
            "company": str(active.get("company") or ""),
            "gmail_message_id": str(active.get("gmail_message_id") or ""),
            "reply_message_id": str(evidence.get("message_id") or ""),
            "slot": dict(slot),
        }
        self._state["pending_booking"] = pending
        self._persist_state()
        label = self._slot_label(slot)
        contact = pending["contact"] or "the lead"
        return CommandResponse(
            "meeting_confirmation_monitor",
            "healthy",
            f"I found a verified reply from {contact} confirming {label}. I have prepared that exact Calendar event, but I have not booked it. Say 'book it' to approve this specific meeting creation.",
            {
                "execution_status": "meeting_booking_approval_required",
                "meeting_confirmation": {
                    "status": "verified",
                    "contact": contact,
                    "slot": dict(slot),
                    "reply_message_id": pending["reply_message_id"],
                },
                "calendar_booking": {
                    "state": "awaiting_approval",
                    "approval_required": True,
                    "approval_scope": "confirmed_discovery_meeting_booking",
                    "slot": dict(slot),
                },
                "gmail_reply_evidence": dict(evidence),
                "external_action_taken": False,
            },
        )

    def _execute_booking(self, pending: dict[str, Any]) -> CommandResponse:
        calendar = self.dispatchers.get("Google Calendar")
        if calendar is None:
            return CommandResponse(
                "meeting_booking",
                "healthy",
                "The confirmed slot is still awaiting booking, but no live Google Calendar write dispatcher is configured. Nothing has been booked.",
                {
                    "execution_status": "calendar_booking_dispatcher_unavailable",
                    "calendar_booking": {"state": "awaiting_execution", **dict(pending)},
                    "external_action_taken": False,
                },
            )
        slot = pending.get("slot") if isinstance(pending.get("slot"), dict) else {}
        dispatch = {
            "eligible": False,
            "state": "approved_pending_execution",
            "worker": "Google Calendar",
            "instruction": (
                "Create one discovery meeting using exactly the recipient-confirmed slot supplied in the payload. "
                "Do not alter the start/end time and do not create any additional event."
            ),
            "target": {
                "lead_id": str(pending.get("lead_id") or ""),
                "contact": str(pending.get("contact") or ""),
                "company": str(pending.get("company") or ""),
                "area": "commercial",
            },
            "execution_mode": "approval_gated_write",
            "expected_evidence": "verified Calendar event creation with event identifier",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "approval_granted": True,
            "approval_scope": "confirmed_discovery_meeting_booking",
            "payload": {
                "kind": "confirmed_discovery_meeting_booking",
                "slot": dict(slot),
                "gmail_message_id": str(pending.get("gmail_message_id") or ""),
                "reply_message_id": str(pending.get("reply_message_id") or ""),
            },
        }
        try:
            evidence = calendar(dict(dispatch))
        except Exception as exc:
            return CommandResponse(
                "meeting_booking",
                "healthy",
                f"I attempted the approved Calendar booking, but it did not return verified evidence: {exc}. The booking remains pending.",
                {
                    "execution_status": "calendar_booking_failed",
                    "calendar_booking": {"state": "pending", **dict(pending)},
                    "external_action_taken": False,
                },
            )
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        event_id = str(evidence.get("event_id") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not event_id:
            return CommandResponse(
                "meeting_booking",
                "healthy",
                f"I attempted the approved Calendar booking, but the returned evidence was not sufficient to prove one event was created ({reason if not verified else 'missing event identifier'}). The booking remains pending.",
                {
                    "execution_status": "calendar_booking_unverified",
                    "calendar_booking": {"state": "pending", **dict(pending)},
                    "calendar_evidence": evidence if isinstance(evidence, dict) else {},
                    "external_action_taken": False,
                },
            )
        self._state["pending_booking"] = None
        self._state["active_monitor"] = None
        self._state["proposal"] = None
        self._persist_state()
        label = self._slot_label(slot)
        return CommandResponse(
            "meeting_booking",
            "healthy",
            f"Booked. Google Calendar returned verified creation evidence for {label} with event {event_id}. I will treat the discovery meeting as confirmed, not merely proposed.",
            {
                "execution_status": "discovery_booking_verified",
                "calendar_booking": {
                    "state": "verified",
                    "approval_required": True,
                    "approval_scope": "confirmed_discovery_meeting_booking",
                    "event_id": event_id,
                    "slot": dict(slot),
                    "lead_id": str(pending.get("lead_id") or ""),
                    "contact": str(pending.get("contact") or ""),
                    "company": str(pending.get("company") or ""),
                },
                "calendar_evidence": dict(evidence),
                "external_action_taken": True,
            },
        )

    @staticmethod
    def _gmail_read_dispatch(active: dict[str, Any]) -> dict[str, Any]:
        message_id = str(active.get("gmail_message_id") or "")
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Gmail",
            "instruction": (
                f"Read the Gmail thread anchored by discovery reply {message_id}. Return only new inbound reply evidence. "
                "Include reply_found, sender, body/snippet, message_id and thread_id. Do not send, label, archive or mutate Gmail."
            ),
            "target": {
                "lead_id": str(active.get("lead_id") or ""),
                "contact": str(active.get("contact") or ""),
                "company": str(active.get("company") or ""),
                "area": "commercial",
            },
            "execution_mode": "autonomous_read",
            "expected_evidence": "verified Gmail thread read with confirmation reply evidence",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "commercial_meeting_confirmation_monitor", "gmail_message_id": message_id},
        }

    @classmethod
    def _matching_slots(cls, active: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, Any]]:
        reply = cls._normalise(cls._reply_text(evidence))
        if not reply:
            return []
        matches: list[dict[str, Any]] = []
        for slot in active.get("available_slots", ()):
            if not isinstance(slot, dict):
                continue
            tokens = cls._slot_tokens(slot)
            if tokens and all(token in reply for token in tokens):
                matches.append(dict(slot))
        return matches

    @classmethod
    def _slot_tokens(cls, slot: dict[str, Any]) -> tuple[str, ...]:
        label = cls._slot_label(slot)
        day_match = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", label, re.I)
        time_match = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", label)
        tokens = []
        if day_match:
            tokens.append(day_match.group(1).casefold())
        if time_match:
            tokens.append(time_match.group(0).casefold())
        start = str(slot.get("start") or "").strip()
        if not tokens and start:
            tokens.append(cls._normalise(start))
        return tuple(tokens)

    @staticmethod
    def _structured_slots(availability: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("available_slots", "slots", "options"):
            value = availability.get(key)
            if isinstance(value, list):
                slots = [dict(item) for item in value if isinstance(item, dict)]
                valid = [
                    item
                    for item in slots
                    if str(item.get("start") or "").strip()
                    and str(item.get("end") or "").strip()
                ]
                if valid:
                    return valid
        return []

    @staticmethod
    def _slot_label(slot: dict[str, Any]) -> str:
        return str(slot.get("label") or slot.get("summary") or slot.get("start") or "the confirmed slot").strip()

    @staticmethod
    def _reply_text(evidence: dict[str, Any]) -> str:
        return TonyConfirmedMeetingBookingCommandService._first_text(
            evidence,
            ("body", "content", "thread_content", "snippet", "summary", "result"),
        )

    @staticmethod
    def _first_text(value: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return " ".join(item.split())
        return ""

    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(value.casefold().replace(" at ", " ").split())

    @staticmethod
    def _blocked(
        status: str,
        message: str,
        active: dict[str, Any],
        *,
        evidence: dict[str, Any] | None = None,
    ) -> CommandResponse:
        data: dict[str, Any] = {
            "execution_status": status,
            "meeting_confirmation_monitor": {"status": "active", **dict(active)},
            "external_action_taken": False,
        }
        if evidence is not None:
            data["gmail_reply_evidence"] = dict(evidence)
        return CommandResponse("meeting_confirmation_monitor", "healthy", message + " Nothing has been booked.", data)

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"proposal": None, "active_monitor": None, "pending_booking": None}
        if not isinstance(payload, dict):
            return {"proposal": None, "active_monitor": None, "pending_booking": None}
        return {
            "proposal": payload.get("proposal") if isinstance(payload.get("proposal"), dict) else None,
            "active_monitor": payload.get("active_monitor") if isinstance(payload.get("active_monitor"), dict) else None,
            "pending_booking": payload.get("pending_booking") if isinstance(payload.get("pending_booking"), dict) else None,
        }

    def _persist_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.store_path)
