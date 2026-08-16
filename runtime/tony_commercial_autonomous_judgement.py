from __future__ import annotations

from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import DispatchHandler
from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_autonomous_result import TonyPersistentAutonomousResultCommandService


class TonyCommercialAutonomousJudgementCommandService(TonyPersistentAutonomousResultCommandService):
    """Turn verified commercial Gmail reads into Tony-owned executive judgement.

    Worker evidence proves what was read. Tony, not the worker, owns the commercial
    disposition and consequential recommendation. The judgement stays conservative:
    automatic replies and ambiguous messages do not create an executable next action.
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
    _POSITIVE_MARKERS = (
        "interested",
        "sounds good",
        "tell me more",
        "let's talk",
        "lets talk",
        "book a call",
        "set up a call",
        "schedule a call",
        "happy to chat",
        "worth a conversation",
        "send over",
        "would love to",
        "availability next week",
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

        if disposition == "positive_intent":
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
        dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        if worker != "gmail" or str(dispatch.get("execution_mode") or "") != "autonomous_read":
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

        if any(marker in text for marker in cls._AUTO_REPLY_MARKERS):
            disposition = "automatic_reply"
            recommendation = ""
        elif any(marker in text for marker in cls._DECLINE_MARKERS):
            disposition = "declined"
            recommendation = "Update the lead record to closed or declined and stop active follow-up."
        elif any(marker in text for marker in cls._POSITIVE_MARKERS):
            disposition = "positive_intent"
            recommendation = "Reply to the lead and propose a discovery conversation, using the verified thread as context."
        else:
            disposition = "reply_received"
            recommendation = ""

        if recommendation:
            evidence["recommended_next_action"] = recommendation
        context["evidence"] = evidence
        context["commercial_judgement"] = {
            "disposition": disposition,
            "recommended_next_action": recommendation,
            "judgement_owner": "Tony",
            "evidence_basis": "verified_gmail_read",
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
