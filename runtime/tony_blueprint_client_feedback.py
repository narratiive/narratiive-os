from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintClientFeedbackCommandService:
    """Track verified client acknowledgement or feedback after Blueprint delivery.

    A verified Notion delivery state proves only that Narratiive recorded the exact
    client-accessible artifact as delivered. This layer performs read-only Gmail
    checks for subsequent client evidence and classifies it conservatively. It never
    treats acknowledgement as acceptance, never mutates Notion, and never sends a
    reply or commissions revision work.
    """

    CHECK_MARKERS = {
        "check growth blueprint feedback",
        "check blueprint feedback",
        "check client feedback",
        "any growth blueprint feedback",
        "any blueprint feedback",
        "has the client responded",
        "has the client replied",
        "did the client respond",
    }
    ACKNOWLEDGEMENT_MARKERS = (
        "received", "got it", "thank you", "thanks", "we have it", "i have it",
        "came through", "received this", "received the blueprint",
    )
    POSITIVE_MARKERS = (
        "looks good", "looks great", "really useful", "very useful", "helpful",
        "makes sense", "strong work", "great work", "happy with", "pleased with",
    )
    REVISION_MARKERS = (
        "change", "changes", "revise", "revision", "amend", "amendment",
        "question", "questions", "clarify", "clarification", "could you", "can you",
        "feedback", "not clear", "unclear", "missing", "add", "remove",
    )
    NEGATIVE_MARKERS = (
        "not what we expected", "not what i expected", "doesn't work", "does not work",
        "not happy", "unhappy", "disappointed", "concerned", "doesn't reflect",
        "does not reflect", "off brief",
    )

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
        active = self.state.get("active") if isinstance(self.state.get("active"), dict) else None
        if active and normalized in self.CHECK_MARKERS:
            return self._check(active)

        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "blueprint_delivery_notion_sync_verified":
            return response
        delivery = data.get("blueprint_delivery_state") if isinstance(data.get("blueprint_delivery_state"), dict) else {}
        project_id = str(delivery.get("delivery_project_record_id") or "").strip()
        file_id = str(delivery.get("growth_blueprint_file_id") or "").strip()
        delivery_url = str(delivery.get("delivery_url") or "").strip()
        if not project_id or not file_id or not delivery_url:
            return response

        active = {
            "delivery_project_record_id": project_id,
            "lead_id": str(delivery.get("lead_id") or ""),
            "contact": str(delivery.get("contact") or ""),
            "company": str(delivery.get("company") or ""),
            "growth_blueprint_file_id": file_id,
            "delivery_url": delivery_url,
            "notion_record_id": str(data.get("notion_record_id") or delivery.get("notion_record_id") or ""),
            "seen_message_ids": [],
        }
        existing = self.state.get("active") if isinstance(self.state.get("active"), dict) else None
        if existing and existing.get("delivery_project_record_id") == project_id and existing.get("growth_blueprint_file_id") == file_id:
            active["seen_message_ids"] = list(existing.get("seen_message_ids", []))
        self.state["active"] = active
        self._persist()
        return self._check(active, base=response)

    def _check(self, active: dict[str, Any], *, base: CommandResponse | None = None) -> CommandResponse:
        gmail = self.dispatchers.get("Gmail")
        if gmail is None:
            return self._response(
                active,
                base,
                "blueprint_feedback_monitor_dispatcher_unavailable",
                " Client feedback monitoring is ready, but no live Gmail read dispatcher is configured. I cannot verify acknowledgement or feedback yet.",
            )
        dispatch = self._gmail_read_dispatch(active)
        try:
            evidence = gmail(dict(dispatch))
        except Exception as exc:
            return self._response(
                active,
                base,
                "blueprint_feedback_monitor_read_failed",
                f" The read-only client feedback check failed: {exc}. I am not inferring acknowledgement or acceptance.",
            )
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return self._response(
                active,
                base,
                "blueprint_feedback_monitor_unverified",
                f" Gmail returned possible client feedback, but it was not decision-grade evidence ({reason}). I am not inferring acknowledgement or acceptance.",
                evidence,
            )
        if not self._feedback_found(active, evidence):
            return self._response(
                active,
                base,
                "blueprint_feedback_monitor_active",
                " I checked the verified client correspondence and found no new decision-grade Growth Blueprint feedback yet.",
                evidence,
            )
        return self._record_feedback(active, evidence, base)

    def _record_feedback(self, active: dict[str, Any], evidence: dict[str, Any], base: CommandResponse | None) -> CommandResponse:
        text = self._feedback_text(evidence)
        folded = text.casefold()
        if any(marker in folded for marker in self.NEGATIVE_MARKERS):
            disposition = "negative_feedback"
            recommendation = "Review the verified client concern and prepare a bounded revision response before changing the delivered artifact."
            acknowledgement = True
            revision_requested = True
        elif any(marker in folded for marker in self.REVISION_MARKERS):
            disposition = "feedback_or_revision_request"
            recommendation = "Review the verified feedback, identify the exact requested changes and prepare an internal revision plan before altering the client artifact."
            acknowledgement = True
            revision_requested = True
        elif any(marker in folded for marker in self.POSITIVE_MARKERS):
            disposition = "positive_feedback"
            recommendation = "Treat this as positive verified feedback, but do not infer formal acceptance or completion unless the client explicitly confirms that separately."
            acknowledgement = True
            revision_requested = False
        elif any(marker in folded for marker in self.ACKNOWLEDGEMENT_MARKERS):
            disposition = "delivery_acknowledged"
            recommendation = "Treat this only as verified acknowledgement that the client received or saw the Growth Blueprint. Do not infer acceptance, satisfaction or project completion."
            acknowledgement = True
            revision_requested = False
        else:
            disposition = "client_feedback_received"
            recommendation = "Review the verified client response before deciding whether revision, discussion or no action is appropriate."
            acknowledgement = True
            revision_requested = False

        message_id = str(evidence.get("message_id") or evidence.get("gmail_message_id") or "").strip()
        seen = [str(item) for item in active.get("seen_message_ids", []) if item]
        if message_id and message_id not in seen:
            seen.append(message_id)
        active = {**active, "seen_message_ids": seen[-100:], "last_feedback_message_id": message_id}
        self.state["active"] = active
        self.state["last_feedback"] = {
            "message_id": message_id,
            "disposition": disposition,
            "client_acknowledged": acknowledgement,
            "client_accepted": False,
            "revision_requested": revision_requested,
            "evidence": dict(evidence),
        }
        self._persist()

        label = str(active.get("company") or active.get("contact") or "the client")
        prefix = base.message if base is not None else "Growth Blueprint feedback check complete."
        return CommandResponse(
            "blueprint_client_feedback",
            "healthy",
            f"{prefix} I found new verified Growth Blueprint feedback from {label}. My judgement: {recommendation}",
            {
                "execution_status": "blueprint_client_feedback_verified",
                "blueprint_feedback": {
                    **active,
                    "disposition": disposition,
                    "client_acknowledged": acknowledgement,
                    "client_accepted": False,
                    "revision_requested": revision_requested,
                    "recommended_next_action": recommendation,
                },
                "gmail_feedback_evidence": dict(evidence),
                "external_action_taken": False,
            },
        )

    @staticmethod
    def _gmail_read_dispatch(active: dict[str, Any]) -> dict[str, Any]:
        file_id = str(active.get("growth_blueprint_file_id") or "")
        delivery_url = str(active.get("delivery_url") or "")
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Gmail",
            "instruction": (
                "Search read-only for new inbound client correspondence about the exact delivered Growth Blueprint. "
                f"Ground the match in delivery project {active.get('delivery_project_record_id', '')}, Drive file {file_id}, "
                f"delivery URL {delivery_url}, contact {active.get('contact', '')}, and company {active.get('company', '')}. "
                "Return feedback_found=false when no decision-grade match exists. When feedback exists, return sender, received time, body/snippet and message/thread identifiers. "
                "Do not send, label, archive or mutate Gmail. Do not treat the original outbound/share notification as client feedback."
            ),
            "target": {
                "lead_id": str(active.get("lead_id") or ""),
                "contact": str(active.get("contact") or ""),
                "company": str(active.get("company") or ""),
                "area": "delivery",
            },
            "execution_mode": "autonomous_read",
            "expected_evidence": "verified Gmail read with feedback status, sender and message/thread identifiers",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {
                "kind": "growth_blueprint_client_feedback_monitor",
                "delivery_project_record_id": str(active.get("delivery_project_record_id") or ""),
                "growth_blueprint_file_id": file_id,
                "delivery_url": delivery_url,
                "seen_message_ids": list(active.get("seen_message_ids", [])),
            },
        }

    @classmethod
    def _feedback_found(cls, active: dict[str, Any], evidence: dict[str, Any]) -> bool:
        if evidence.get("feedback_found") is False or evidence.get("reply_found") is False:
            return False
        message_id = str(evidence.get("message_id") or evidence.get("gmail_message_id") or "").strip()
        if message_id and message_id in {str(item) for item in active.get("seen_message_ids", []) if item}:
            return False
        return bool(cls._feedback_text(evidence)) and bool(
            evidence.get("feedback_found") is True or evidence.get("reply_found") is True or message_id
        )

    @staticmethod
    def _feedback_text(evidence: dict[str, Any]) -> str:
        for key in ("body", "content", "thread_content", "snippet", "summary", "result"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return ""

    def _response(
        self,
        active: dict[str, Any],
        base: CommandResponse | None,
        status: str,
        suffix: str,
        evidence: dict[str, Any] | None = None,
    ) -> CommandResponse:
        data: dict[str, Any] = {
            "execution_status": status,
            "blueprint_feedback": {**active, "client_acknowledged": False, "client_accepted": False},
            "external_action_taken": False,
        }
        if evidence is not None:
            data["gmail_feedback_evidence"] = dict(evidence)
        return CommandResponse(
            "blueprint_client_feedback",
            "healthy",
            (base.message if base is not None else "Growth Blueprint feedback check.") + suffix,
            data,
        )

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"active": None, "last_feedback": None}
        if not isinstance(value, dict):
            return {"active": None, "last_feedback": None}
        value.setdefault("active", None)
        value.setdefault("last_feedback", None)
        return value

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.store_path)
