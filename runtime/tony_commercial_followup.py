from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TonyCommercialFollowupCommandService:
    """Monitor verified outreach and branch safely on returned Gmail evidence.

    The monitor is durable across restarts. Gmail checks are read-only and may run
    autonomously. Genuine replies are classified into a grounded next step; when no
    reply exists by the three-business-day deadline, Claude may prepare (never send)
    a tailored follow-up for Tony review.
    """

    _CHECK_MARKERS = {
        "check replies",
        "check reply",
        "check follow up",
        "check follow-up",
        "follow up check",
        "follow-up check",
        "any reply",
        "any replies",
    }
    _MEETING_MARKERS = (
        "let's talk",
        "lets talk",
        "book a call",
        "set up a call",
        "schedule a call",
        "happy to chat",
        "worth a conversation",
        "when are you free",
        "when can you talk",
        "availability next week",
    )
    _INFORMATION_MARKERS = (
        "tell me more",
        "send over",
        "more information",
        "more info",
        "can you explain",
        "what would this involve",
        "what does this involve",
    )
    _POSITIVE_MARKERS = ("interested", "sounds good", "would love to")
    _DECLINE_MARKERS = (
        "not interested",
        "no thanks",
        "no thank you",
        "not for us",
        "not a fit",
        "please unsubscribe",
        "remove me",
        "we'll pass",
        "we will pass",
    )

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._state = self._load_state()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        active = self._state.get("active") if isinstance(self._state.get("active"), dict) else None
        if active and (normalized in self._CHECK_MARKERS or self._now() >= self._parse_time(active["follow_up_due_at"])):
            return self._check_monitor(active)

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
        active = {
            "gmail_message_id": message_id,
            "lead_id": str(target.get("lead_id") or ""),
            "contact": str(target.get("contact") or ""),
            "company": str(target.get("company") or ""),
            "started_at": sent_at.isoformat(),
            "follow_up_due_at": due.isoformat(),
        }
        self._state["active"] = active
        self._persist_state()
        return self._check_monitor(active, base_response=response)

    def _check_monitor(
        self,
        active: dict[str, Any],
        *,
        base_response: CommandResponse | None = None,
    ) -> CommandResponse:
        dispatch = self._gmail_read_dispatch(active)
        handler = self.dispatchers.get("Gmail")
        if handler is None:
            return self._monitor_response(
                active,
                base_response=base_response,
                status="reply_monitor_dispatcher_unavailable",
                suffix=" The reply monitor is active, but no live Gmail read dispatcher is configured, so I cannot verify whether a reply has arrived yet.",
            )
        try:
            evidence = handler(dict(dispatch))
        except Exception as exc:
            return self._monitor_response(
                active,
                base_response=base_response,
                status="reply_monitor_read_failed",
                suffix=f" I attempted the read-only Gmail reply check, but it did not return usable evidence: {exc}",
            )

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return self._monitor_response(
                active,
                base_response=base_response,
                status="reply_monitor_read_unverified",
                suffix=f" Gmail returned data for the reply check, but it was not strong enough to treat as verified ({reason}).",
                evidence=evidence,
            )

        if self._reply_found(active, evidence):
            self._state["active"] = None
            self._persist_state()
            return self._branch_reply(active, evidence, base_response=base_response)

        due = self._parse_time(active["follow_up_due_at"])
        if self._now() < due:
            return self._monitor_response(
                active,
                base_response=base_response,
                status="reply_monitor_active",
                suffix=f" I checked the verified Gmail thread and there is no genuine reply yet. The follow-up remains due on {due.date().isoformat()}.",
                evidence=evidence,
            )
        return self._prepare_follow_up(active, evidence, base_response=base_response)

    def _branch_reply(
        self,
        active: dict[str, Any],
        evidence: dict[str, Any],
        *,
        base_response: CommandResponse | None,
    ) -> CommandResponse:
        text = self._reply_text(evidence)
        folded = text.casefold()
        contact = str(active.get("contact") or "the lead").strip() or "the lead"
        disposition = "reply_received"
        recommendation = "Review the verified reply before choosing a consequential response."
        handoff = None

        if any(marker in folded for marker in self._DECLINE_MARKERS):
            disposition = "declined"
            recommendation = "Stop active follow-up and prepare the authoritative commercial record for closure; do not mutate Notion without the existing approval boundary."
        elif any(marker in folded for marker in self._MEETING_MARKERS):
            disposition = "meeting_intent"
            recommendation = "Check Calendar availability for the next five business days, then prepare a concise discovery reply using only verified times."
            handoff = self._safe_handoff(
                worker="Google Calendar",
                target=active,
                instruction=(
                    f"Check availability for the next five business days for a discovery conversation with {contact}. "
                    "Return available slots with calendar source identifiers. Read only: do not create, move or delete any event."
                ),
                kind="commercial_calendar_availability",
            )
        elif any(marker in folded for marker in self._INFORMATION_MARKERS):
            disposition = "information_request"
            recommendation = "Prepare a concise answer to the question using the verified thread and existing evidence before pushing for a meeting."
            handoff = self._safe_handoff(
                worker="Claude",
                target=active,
                instruction=(
                    f"Prepare a concise reply to {contact}'s verified information request using only the supplied Gmail reply evidence and existing grounded commercial context. "
                    "Answer what they asked first. Do not send the email or change external state."
                ),
                kind="commercial_information_reply_prepare",
            )
        elif any(marker in folded for marker in self._POSITIVE_MARKERS):
            disposition = "positive_intent"
            recommendation = "Prepare a concise acknowledgement and offer discovery as the next option; keep the eventual send approval-gated."
            handoff = self._safe_handoff(
                worker="Claude",
                target=active,
                instruction=(
                    f"Prepare a concise, tailored reply to {contact}'s verified positive response. Acknowledge the interest and offer a discovery conversation as the next option. "
                    "Do not send the email or change external state."
                ),
                kind="commercial_positive_reply_prepare",
            )

        data: dict[str, Any] = {
            "execution_status": "commercial_reply_verified",
            "reply_monitor": {"status": "reply_received", **dict(active)},
            "gmail_reply_evidence": dict(evidence),
            "commercial_judgement": {
                "disposition": disposition,
                "recommended_next_action": recommendation,
                "evidence_basis": "verified_gmail_reply_monitor",
                "judgement_owner": "Tony",
            },
            "external_action_taken": False,
        }
        if handoff is not None:
            data["execution_handoff"] = handoff
            data["execution_status"] = "commercial_reply_next_step_ready"
        prefix = base_response.message if base_response is not None else "Reply check complete."
        return CommandResponse(
            command="commercial_reply_monitor",
            status="healthy",
            message=f"{prefix} I found a genuine verified reply from {contact}. My judgement: {recommendation}",
            data=data,
        )

    def _prepare_follow_up(
        self,
        active: dict[str, Any],
        gmail_evidence: dict[str, Any],
        *,
        base_response: CommandResponse | None,
    ) -> CommandResponse:
        claude_dispatch = self._safe_handoff(
            worker="Claude",
            target=active,
            instruction=(
                f"Prepare a short, tailored follow-up email for {active.get('contact') or 'this lead'} because the verified Gmail thread has no genuine reply after three business days. "
                "Use the original commercial context, be useful rather than needy, and return a subject plus body for Tony review. Do not send it or change external state."
            ),
            kind="commercial_no_reply_follow_up_prepare",
        )["dispatch"]
        handler = self.dispatchers.get("Claude")
        if handler is None:
            return self._follow_up_response(active, gmail_evidence, base_response, "follow_up_preparation_dispatcher_unavailable", None)
        try:
            evidence = handler(dict(claude_dispatch))
        except Exception:
            return self._follow_up_response(active, gmail_evidence, base_response, "follow_up_preparation_failed", None)
        verified, _ = TonyAutonomousDispatchCommandService._verify_evidence(claude_dispatch, evidence)
        if not verified:
            return self._follow_up_response(active, gmail_evidence, base_response, "follow_up_preparation_unverified", evidence)
        self._state["active"] = None
        self._persist_state()
        return self._follow_up_response(active, gmail_evidence, base_response, "follow_up_draft_prepared", evidence)

    def _follow_up_response(
        self,
        active: dict[str, Any],
        gmail_evidence: dict[str, Any],
        base_response: CommandResponse | None,
        status: str,
        claude_evidence: dict[str, Any] | None,
    ) -> CommandResponse:
        prefix = base_response.message if base_response is not None else "Follow-up check complete."
        data: dict[str, Any] = {
            "execution_status": status,
            "reply_monitor": {"status": "follow_up_due", **dict(active)},
            "gmail_reply_evidence": dict(gmail_evidence),
            "external_action_taken": False,
        }
        if claude_evidence:
            data["follow_up_draft_evidence"] = dict(claude_evidence)
            suffix = " There is still no genuine reply after three business days. Claude has returned a verified follow-up draft for Tony review; nothing has been sent."
        elif status == "follow_up_preparation_dispatcher_unavailable":
            suffix = " There is still no genuine reply after three business days, but no live Claude dispatcher is configured to prepare the follow-up. Nothing has been sent."
        else:
            suffix = " There is still no genuine reply after three business days. I attempted follow-up preparation, but it did not return verified work, so nothing is ready to send."
        return CommandResponse("commercial_follow_up", "healthy", prefix + suffix, data)

    def _monitor_response(
        self,
        active: dict[str, Any],
        *,
        base_response: CommandResponse | None,
        status: str,
        suffix: str,
        evidence: dict[str, Any] | None = None,
    ) -> CommandResponse:
        prefix = base_response.message if base_response is not None else "Reply monitor check."
        data: dict[str, Any] = {
            "execution_status": status,
            "reply_monitor": {"status": "active", **dict(active)},
            "external_action_taken": False,
        }
        if evidence is not None:
            data["gmail_reply_evidence"] = dict(evidence)
        return CommandResponse("commercial_reply_monitor", "healthy", prefix + suffix, data)

    @staticmethod
    def _gmail_read_dispatch(active: dict[str, Any]) -> dict[str, Any]:
        message_id = str(active.get("gmail_message_id") or "")
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Gmail",
            "instruction": (
                f"Read the Gmail thread anchored by outbound message {message_id}. Return only new inbound reply evidence, including sender, received time, body/snippet and thread/message identifiers. "
                "If no genuine inbound reply exists, explicitly return reply_found=false. Do not send, label, archive or mutate Gmail."
            ),
            "target": {
                "lead_id": str(active.get("lead_id") or ""),
                "contact": str(active.get("contact") or ""),
                "company": str(active.get("company") or ""),
                "area": "commercial",
            },
            "execution_mode": "autonomous_read",
            "expected_evidence": "verified Gmail thread read with message/thread identifiers and reply status",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "commercial_reply_monitor", "gmail_message_id": message_id},
        }

    @staticmethod
    def _safe_handoff(*, worker: str, target: dict[str, Any], instruction: str, kind: str) -> dict[str, Any]:
        mode = "autonomous_read" if worker == "Google Calendar" else "autonomous_prepare"
        dispatch = {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": worker,
            "instruction": instruction,
            "target": {
                "lead_id": str(target.get("lead_id") or ""),
                "contact": str(target.get("contact") or ""),
                "company": str(target.get("company") or ""),
                "area": "commercial",
            },
            "execution_mode": mode,
            "expected_evidence": "verified read evidence" if mode == "autonomous_read" else "verified prepared work product",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": kind},
        }
        return {"worker": worker, "approval_required": False, "execution_mode": mode, "action": instruction, "dispatch": dispatch}

    @classmethod
    def _reply_found(cls, active: dict[str, Any], evidence: dict[str, Any]) -> bool:
        if evidence.get("reply_found") is False:
            return False
        text = cls._reply_text(evidence)
        if not text:
            return False
        inbound_id = str(evidence.get("message_id") or "").strip()
        outbound_id = str(active.get("gmail_message_id") or "").strip()
        return evidence.get("reply_found") is True or bool(inbound_id and inbound_id != outbound_id)

    @staticmethod
    def _reply_text(evidence: dict[str, Any]) -> str:
        for key in ("body", "content", "thread_content", "snippet", "summary", "result"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return ""

    def _load_state(self) -> dict[str, Any]:
        if self.store_path is None:
            return {"active": None}
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"active": None}
        return payload if isinstance(payload, dict) else {"active": None}

    def _persist_state(self) -> None:
        if self.store_path is None:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.store_path)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _add_business_days(value: datetime, days: int) -> datetime:
        current = value
        remaining = days
        while remaining:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current
