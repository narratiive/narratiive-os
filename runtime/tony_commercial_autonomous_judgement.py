from __future__ import annotations

from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import DispatchHandler
from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_autonomous_result import TonyPersistentAutonomousResultCommandService


class TonyCommercialAutonomousJudgementCommandService(TonyPersistentAutonomousResultCommandService):
    """Turn verified commercial worker reads into Tony-owned executive judgement.

    Worker evidence proves what was read. Tony, not the worker, owns the commercial
    disposition and consequential recommendation. The judgement stays conservative:
    automatic replies and ambiguous messages do not create an executable next action,
    and calendar availability only advances a meeting sequence when the read is clearly
    tied to a commercial lead and returns substantive availability evidence.
    """

    _AUTO_REPLY_MARKERS = (
        "automatic reply",
        "auto reply",
        "autoreply",
        "out of office",
        "away from the office",
        "currently away",
    )
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
    _MEETING_MARKERS = (
        "let's talk",
        "lets talk",
        "book a call",
        "set up a call",
        "schedule a call",
        "happy to chat",
        "worth a conversation",
        "availability next week",
        "when are you free",
        "when can you talk",
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
    _POSITIVE_MARKERS = (
        "interested",
        "sounds good",
        "would love to",
    )
    _COMMERCIAL_TEXT_KEYS = (
        "content",
        "thread_content",
        "body",
        "snippet",
        "summary",
        "analysis",
        "result",
    )
    _CALENDAR_RESULT_KEYS = (
        "availability",
        "available_slots",
        "slots",
        "options",
        "summary",
        "analysis",
        "result",
    )

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(command_service, dispatchers=dispatchers, **kwargs)
        if self._last_verified_result is not None and self._enrich_context(self._last_verified_result):
            self._persist_context(self._last_verified_result)

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        response = super().execute(command, objects)
        context = self._last_verified_result
        if context is None or not self._enrich_context(context):
            return response

        self._persist_context(context)
        judgement = context.get("commercial_judgement")
        if not isinstance(judgement, dict):
            return response

        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["commercial_judgement"] = dict(judgement)
        disposition = str(judgement.get("disposition") or "").strip()
        recommendation = str(judgement.get("recommended_next_action") or "").strip()

        if disposition == "meeting_intent":
            suffix = f" My judgement: they are signalling a conversation. I recommend: {recommendation}"
        elif disposition == "availability_verified":
            suffix = (
                " The Calendar check returned verified availability for this commercial lead. "
                f"I recommend: {recommendation}"
            )
        elif disposition == "information_request":
            suffix = f" My judgement: they want more substance before a meeting. I recommend: {recommendation}"
        elif disposition == "positive_intent":
            suffix = f" My judgement: this is positive commercial intent. I recommend: {recommendation}"
        elif disposition == "declined":
            suffix = f" My judgement: this is a decline. I recommend: {recommendation}"
        elif disposition == "automatic_reply":
            suffix = " My judgement: this is an automatic reply, not evidence of engagement, so I would keep the follow-up open."
        else:
            suffix = " My judgement: the reply is not clear enough to justify a consequential next move yet."

        return CommandResponse(
            command=response.command,
            status=response.status,
            message=response.message + suffix,
            data=data,
        )

    @classmethod
    def _enrich_context(cls, context: dict[str, Any]) -> bool:
        if isinstance(context.get("commercial_judgement"), dict):
            return False

        worker = str(context.get("worker") or "").strip().casefold()
        if worker in {"google calendar", "calendar"}:
            return cls._enrich_calendar_context(context)
        if worker != "gmail":
            return False

        dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        if str(dispatch.get("execution_mode") or "") != "autonomous_read":
            return False
        if not cls._requires_decision_grade_read(dispatch):
            return False

        text = cls._commercial_text(evidence).casefold()
        if not text:
            return False

        worker_recommendation = str(
            evidence.get("recommended_next_action") or evidence.get("next_action") or evidence.get("recommendation") or ""
        ).strip()
        if worker_recommendation:
            evidence["worker_recommended_next_action"] = worker_recommendation
            evidence.pop("recommended_next_action", None)
            evidence.pop("next_action", None)
            evidence.pop("recommendation", None)

        execution_next_action = ""
        if any(marker in text for marker in cls._AUTO_REPLY_MARKERS):
            disposition = "automatic_reply"
            recommendation = ""
        elif any(marker in text for marker in cls._DECLINE_MARKERS):
            disposition = "declined"
            recommendation = "Update the lead record to closed or declined and stop active follow-up."
        elif any(marker in text for marker in cls._MEETING_MARKERS):
            disposition = "meeting_intent"
            recommendation = "Check calendar availability for the next five business days, then prepare a concise discovery reply with two suitable times."
            execution_next_action = "Check calendar availability for the next five business days."
        elif any(marker in text for marker in cls._INFORMATION_MARKERS):
            disposition = "information_request"
            recommendation = "Prepare a concise, tailored answer to the lead's question using the verified thread; do not force a meeting before answering what they asked."
        elif any(marker in text for marker in cls._POSITIVE_MARKERS):
            disposition = "positive_intent"
            recommendation = "Reply to the lead, acknowledge the interest, and suggest a discovery conversation as the next option."
        else:
            disposition = "reply_received"
            recommendation = ""

        if recommendation:
            evidence["recommended_next_action"] = recommendation
        if execution_next_action:
            evidence["execution_next_action"] = execution_next_action
        context["evidence"] = evidence
        context["commercial_judgement"] = {
            "disposition": disposition,
            "recommended_next_action": recommendation,
            "execution_next_action": execution_next_action,
            "judgement_owner": "Tony",
            "evidence_basis": "verified_gmail_read",
        }
        return True

    @classmethod
    def _enrich_calendar_context(cls, context: dict[str, Any]) -> bool:
        dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        target = dispatch.get("target") if isinstance(dispatch.get("target"), dict) else {}
        instruction = str(dispatch.get("instruction") or dispatch.get("action") or "").strip().casefold()

        if str(dispatch.get("execution_mode") or "") != "autonomous_read":
            return False
        if str(target.get("area") or "").strip().casefold() != "commercial":
            return False
        if not (target.get("lead_id") or target.get("contact")):
            return False
        if not any(marker in instruction for marker in ("availability", "free time", "calendar")):
            return False

        availability = cls._first_rendered(evidence, cls._CALENDAR_RESULT_KEYS)
        if not availability:
            return False

        contact = str(target.get("contact") or "the lead").strip() or "the lead"
        recommendation = (
            f"Prepare a concise discovery reply to {contact} offering two suitable times from the verified Calendar result. "
            "Use only the returned availability and do not invent or extend any time slot."
        )
        evidence["recommended_next_action"] = recommendation
        evidence["verified_availability_summary"] = availability
        context["evidence"] = evidence
        context["commercial_judgement"] = {
            "disposition": "availability_verified",
            "recommended_next_action": recommendation,
            "execution_next_action": "",
            "judgement_owner": "Tony",
            "evidence_basis": "verified_calendar_read",
        }
        return True

    @classmethod
    def _commercial_text(cls, evidence: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in cls._COMMERCIAL_TEXT_KEYS:
            rendered = cls._render_result_value(evidence.get(key))
            if rendered:
                parts.append(rendered)
        return " ".join(parts)
