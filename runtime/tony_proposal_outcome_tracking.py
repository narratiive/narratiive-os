from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TonyProposalOutcomeTrackingCommandService:
    """Track what happens after a verified Proposal sent state.

    Proposal delivery is not commercial success. This layer opens a durable,
    read-only Gmail watch anchored to the verified proposal message, classifies
    returned evidence conservatively, and may ask Claude to prepare reversible
    follow-up work. It never marks a deal won, mutates Notion, sends email or
    creates another external commitment.
    """

    _CHECK_MARKERS = {
        "check proposal", "check proposal reply", "check proposal replies",
        "any proposal reply", "any proposal replies", "proposal status",
    }
    _ACCEPTANCE_MARKERS = (
        "we'd like to proceed", "we would like to proceed", "happy to proceed",
        "let's proceed", "lets proceed", "go ahead", "approved", "we accept",
        "accept the proposal", "sounds good to us", "ready to start",
    )
    _DECLINE_MARKERS = (
        "not proceeding", "won't proceed", "will not proceed", "we'll pass",
        "we will pass", "not moving forward", "not going ahead", "decline",
        "not for us", "too expensive",
    )
    _OBJECTION_MARKERS = (
        "budget", "price", "cost", "expensive", "scope", "timeline", "timing",
        "concern", "concerns", "question", "questions", "clarify", "clarification",
        "change", "revise", "revision",
    )

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        active = self.state.get("active") if isinstance(self.state.get("active"), dict) else None
        if active and (normalized in self._CHECK_MARKERS or self._now() >= self._parse_time(active["follow_up_due_at"])):
            return self._check(active)

        response = self.command_service.execute(command, objects)
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "proposal_commercial_state_sync_verified":
            return response
        message_id = str(data.get("gmail_message_id") or "").strip()
        if not message_id:
            return response

        completed = self._proposal_context()
        started = self._now()
        active = {
            "gmail_message_id": message_id,
            "lead_id": str(completed.get("lead_id") or ""),
            "contact": str(completed.get("contact") or ""),
            "company": str(completed.get("company") or ""),
            "started_at": started.isoformat(),
            "follow_up_due_at": self._add_business_days(started, 3).isoformat(),
        }
        self.state["active"] = active
        self._persist()
        return self._check(active, base=response)

    def _proposal_context(self) -> dict[str, Any]:
        inner = getattr(self.command_service, "state", None)
        if isinstance(inner, dict) and isinstance(inner.get("last_completed"), dict):
            return dict(inner["last_completed"])
        return {}

    def _check(self, active: dict[str, Any], *, base: CommandResponse | None = None) -> CommandResponse:
        dispatch = self._gmail_read_dispatch(active)
        gmail = self.dispatchers.get("Gmail")
        if gmail is None:
            return self._response(active, base, "proposal_outcome_monitor_dispatcher_unavailable", " The proposal outcome watch is active, but no live Gmail read dispatcher is configured. I cannot verify a response yet.")
        try:
            evidence = gmail(dict(dispatch))
        except Exception as exc:
            return self._response(active, base, "proposal_outcome_monitor_read_failed", f" The read-only proposal reply check failed: {exc}. I am not inferring an outcome.")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return self._response(active, base, "proposal_outcome_monitor_unverified", f" Gmail returned proposal-thread data, but it was not decision-grade evidence ({reason}). I am not inferring an outcome.", evidence)

        if self._reply_found(active, evidence):
            self.state["active"] = None
            self._persist()
            return self._branch_reply(active, evidence, base)

        due = self._parse_time(active["follow_up_due_at"])
        if self._now() < due:
            return self._response(active, base, "proposal_outcome_monitor_active", f" I checked the verified proposal thread and there is no genuine reply yet. The first follow-up checkpoint is {due.date().isoformat()}.", evidence)
        return self._prepare_silence_follow_up(active, evidence, base)

    def _branch_reply(self, active: dict[str, Any], evidence: dict[str, Any], base: CommandResponse | None) -> CommandResponse:
        text = self._reply_text(evidence)
        folded = text.casefold()
        contact = str(active.get("contact") or "the prospect").strip() or "the prospect"
        handoff = None

        if any(marker in folded for marker in self._DECLINE_MARKERS):
            disposition = "proposal_declined"
            recommendation = "Treat this as a verified decline and prepare the authoritative opportunity for a closed/lost or nurture decision. Do not change Notion without approval."
        elif any(marker in folded for marker in self._ACCEPTANCE_MARKERS):
            disposition = "proposal_acceptance_intent"
            recommendation = "Treat this as verified acceptance intent, not a won deal. Confirm any unresolved scope, commercial terms, contract and payment requirements before changing the opportunity to won or starting delivery."
        elif any(marker in folded for marker in self._OBJECTION_MARKERS):
            disposition = "proposal_objection_or_question"
            recommendation = "Answer the verified objection or question directly before asking for another commitment."
            handoff = self._claude_prepare(active, evidence, "Prepare a concise response to the prospect's verified proposal question or objection. Use only the proposal context and returned Gmail evidence. Address the issue directly, preserve unresolved commercial gaps, and do not send anything or change external state.", "proposal_objection_response_prepare")
        else:
            disposition = "proposal_reply_received"
            recommendation = "Review the verified proposal reply before making a consequential commercial move."

        data: dict[str, Any] = {
            "execution_status": "proposal_outcome_verified",
            "proposal_outcome": {"status": "reply_received", **dict(active)},
            "gmail_reply_evidence": dict(evidence),
            "commercial_judgement": {
                "disposition": disposition,
                "recommended_next_action": recommendation,
                "judgement_owner": "Tony",
                "evidence_basis": "verified_gmail_proposal_thread",
                "deal_won": False,
            },
            "external_action_taken": False,
        }
        if handoff is not None:
            data.update(handoff)
        prefix = base.message if base is not None else "Proposal outcome check complete."
        return CommandResponse("proposal_outcome", "healthy", f"{prefix} I found a genuine verified proposal reply from {contact}. My judgement: {recommendation}", data)

    def _prepare_silence_follow_up(self, active: dict[str, Any], gmail_evidence: dict[str, Any], base: CommandResponse | None) -> CommandResponse:
        prepared = self._claude_prepare(active, gmail_evidence, "Prepare a short, useful proposal follow-up because the verified Gmail thread has no genuine reply after three business days. Refer to the proposal without pressure, surface one practical reason to respond, and return a subject plus body for Tony review. Do not send it or change external state.", "proposal_no_reply_follow_up_prepare")
        prefix = base.message if base is not None else "Proposal outcome check complete."
        if prepared is None:
            return CommandResponse("proposal_outcome", "healthy", prefix + " There is still no genuine proposal reply after three business days, but no live Claude dispatcher is configured. Nothing has been sent.", {"execution_status": "proposal_follow_up_dispatcher_unavailable", "proposal_outcome": dict(active), "gmail_reply_evidence": dict(gmail_evidence), "external_action_taken": False})
        self.state["active"] = None
        self._persist()
        return CommandResponse("proposal_outcome", "healthy", prefix + " There is still no genuine proposal reply after three business days. Claude returned verified follow-up preparation for Tony review; nothing has been sent.", {"execution_status": "proposal_follow_up_draft_prepared", "proposal_outcome": dict(active), "gmail_reply_evidence": dict(gmail_evidence), **prepared, "external_action_taken": False})

    def _claude_prepare(self, active: dict[str, Any], evidence: dict[str, Any], instruction: str, kind: str) -> dict[str, Any] | None:
        claude = self.dispatchers.get("Claude")
        if claude is None:
            return None
        dispatch = {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Claude",
            "instruction": instruction,
            "target": {"lead_id": str(active.get("lead_id") or ""), "contact": str(active.get("contact") or ""), "company": str(active.get("company") or ""), "area": "commercial"},
            "execution_mode": "autonomous_prepare",
            "expected_evidence": "verified prepared work product",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": kind, "gmail_message_id": str(active.get("gmail_message_id") or ""), "reply_evidence": dict(evidence)},
        }
        try:
            result = claude(dict(dispatch))
        except Exception:
            return None
        verified, _ = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, result)
        if not verified:
            return None
        return {"execution_handoff": {"worker": "Claude", "approval_required": False, "execution_mode": "autonomous_prepare", "dispatch": dispatch}, "proposal_follow_up_evidence": dict(result)}

    def _response(self, active: dict[str, Any], base: CommandResponse | None, status: str, suffix: str, evidence: dict[str, Any] | None = None) -> CommandResponse:
        data: dict[str, Any] = {"execution_status": status, "proposal_outcome": {"status": "active", **dict(active)}, "external_action_taken": False}
        if evidence is not None:
            data["gmail_reply_evidence"] = dict(evidence)
        return CommandResponse("proposal_outcome", "healthy", (base.message if base is not None else "Proposal outcome check.") + suffix, data)

    @staticmethod
    def _gmail_read_dispatch(active: dict[str, Any]) -> dict[str, Any]:
        message_id = str(active.get("gmail_message_id") or "")
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Gmail",
            "instruction": f"Read the Gmail thread anchored by verified proposal message {message_id}. Return only new inbound reply evidence with sender, received time, body/snippet, and thread/message identifiers. If none exists, return reply_found=false. Do not send, label, archive or mutate Gmail.",
            "target": {"lead_id": str(active.get("lead_id") or ""), "contact": str(active.get("contact") or ""), "company": str(active.get("company") or ""), "area": "commercial"},
            "execution_mode": "autonomous_read",
            "expected_evidence": "verified Gmail thread read with message/thread identifiers and reply status",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "proposal_outcome_monitor", "gmail_message_id": message_id},
        }

    @classmethod
    def _reply_found(cls, active: dict[str, Any], evidence: dict[str, Any]) -> bool:
        if evidence.get("reply_found") is False:
            return False
        text = cls._reply_text(evidence)
        inbound_id = str(evidence.get("message_id") or "").strip()
        outbound_id = str(active.get("gmail_message_id") or "").strip()
        return bool(text) and (evidence.get("reply_found") is True or bool(inbound_id and inbound_id != outbound_id))

    @staticmethod
    def _reply_text(evidence: dict[str, Any]) -> str:
        for key in ("body", "content", "thread_content", "snippet", "summary", "result"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return ""

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"active": None}
        return value if isinstance(value, dict) else {"active": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)

    def _now(self) -> datetime:
        value = self.clock()
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

    @staticmethod
    def _add_business_days(value: datetime, days: int) -> datetime:
        current = value
        remaining = days
        while remaining:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current
