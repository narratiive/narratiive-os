from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DispatchResult:
    worker: str
    status: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "status": self.status,
            "evidence": dict(self.evidence),
        }


class TonyAutonomousDispatchCommandService:
    """Execute contracts that are either autonomously safe or explicitly approved.

    This layer is deliberately narrow. It never decides that an action is safe and it
    never invents approval; it consumes the risk and approval decisions already made
    upstream. A dispatcher must return structured evidence that satisfies the dispatch
    contract before Tony can say a step actually ran. Verified work is then summarised
    into Tony's visible reply so execution advances the conversation without exposing
    implementation plumbing.
    """

    _SOURCE_ID_KEYS = {
        "source_id",
        "source_ids",
        "thread_id",
        "message_id",
        "message_ids",
        "event_id",
        "event_ids",
        "record_id",
        "record_ids",
        "page_id",
        "page_ids",
        "commit_sha",
        "run_id",
        "url",
    }
    _WORK_PRODUCT_KEYS = {
        "work_product",
        "draft",
        "content",
        "summary",
        "analysis",
        "recommendation",
        "recommendations",
        "options",
        "artifact",
        "result",
    }
    _WRITE_PROOF_KEYS = {
        "sent",
        "created",
        "updated",
        "deleted",
        "published",
        "deployed",
        "merged",
        "committed",
        "mutation_count",
    }
    _EXECUTIVE_RESULT_KEYS = (
        "recommendation",
        "summary",
        "analysis",
        "work_product",
        "draft",
        "content",
        "result",
        "options",
        "recommendations",
        "artifact",
    )
    _RESULT_RECALL_MARKERS = (
        "what did it find",
        "what did they find",
        "what came back",
        "what was the result",
        "what did you get back",
        "tell me what came back",
    )
    _RESULT_RECOMMENDATION_MARKERS = (
        "what do you recommend",
        "what should we do with that",
        "what should i do with that",
        "what next",
        "so what",
    )
    _ACKNOWLEDGEMENT_PREFIXES = ("ok, ", "okay, ", "yes, ", "right, ", "great, ", "fine, ")

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
    ) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self._last_verified_result: dict[str, Any] | None = None

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        if self._last_verified_result is not None:
            if self._matches_follow_up(lowered, self._RESULT_RECALL_MARKERS):
                return self._recall_last_verified_result()
            if self._matches_follow_up(lowered, self._RESULT_RECOMMENDATION_MARKERS):
                return self._recommend_from_last_verified_result()

        response = self.command_service.execute(command, objects)
        return self._dispatch_if_eligible(response)

    def _dispatch_if_eligible(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        handoff = data.get("execution_handoff")
        if not isinstance(handoff, dict):
            return response
        dispatch = handoff.get("dispatch")
        if not isinstance(dispatch, dict):
            return response
        if dispatch.get("execution_truth") != "not_dispatched":
            return response

        autonomous_ready = bool(dispatch.get("eligible")) and dispatch.get("state") == "ready_for_autonomous_dispatch"
        approved_write = (
            str(dispatch.get("execution_mode") or "") == "approval_gated_write"
            and dispatch.get("state") == "approved_pending_execution"
            and dispatch.get("approval_granted") is True
            and handoff.get("approval_granted") is True
        )
        if not autonomous_ready and not approved_write:
            return response

        worker = str(dispatch.get("worker") or "").strip()
        handler = self.dispatchers.get(worker)
        step_kind = "approved" if approved_write else "safe"
        if handler is None:
            return self._with_dispatch_state(
                response,
                data,
                handoff,
                dispatch,
                state="dispatcher_unavailable",
                execution_truth="not_dispatched",
                message_suffix=f" I could not dispatch the {step_kind} {worker or 'worker'} step because no live dispatcher is configured.",
            )

        try:
            evidence = handler(dict(dispatch))
        except Exception as exc:
            return self._with_dispatch_state(
                response,
                data,
                handoff,
                dispatch,
                state="dispatch_failed",
                execution_truth="dispatch_attempted_unverified",
                message_suffix=f" I attempted the {step_kind} {worker} step, but it did not return verified evidence: {exc}",
            )

        verified, reason = self._verify_evidence(dispatch, evidence)
        if not verified:
            return self._with_dispatch_state(
                response,
                data,
                handoff,
                dispatch,
                state="dispatch_unverified",
                execution_truth="dispatch_attempted_unverified",
                message_suffix=(
                    f" I attempted the {step_kind} {worker} step, but the returned evidence did not satisfy the dispatch contract"
                    f" ({reason}), so I am not treating it as complete."
                ),
            )

        result = DispatchResult(worker=worker, status="verified", evidence=evidence)
        executive_result = self._executive_result_summary(worker, dispatch, evidence)
        self._last_verified_result = {
            "worker": worker,
            "dispatch": dict(dispatch),
            "evidence": dict(evidence),
            "executive_result": executive_result,
        }
        updated = self._with_dispatch_state(
            response,
            data,
            handoff,
            dispatch,
            state="dispatch_verified",
            execution_truth="verified_dispatch",
            message_suffix=f" {executive_result}",
        )
        updated.data["dispatch_result"] = result.to_dict()
        updated.data["execution_status"] = "approved_step_verified" if approved_write else "autonomous_step_verified"
        updated.data["executive_result"] = executive_result
        return updated

    def _recall_last_verified_result(self) -> CommandResponse:
        context = dict(self._last_verified_result or {})
        worker = str(context.get("worker") or "the worker").strip()
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        result = self._best_result_text(evidence)
        if result:
            message = f"The verified result from {worker} was: {result}"
        else:
            message = str(context.get("executive_result") or f"{worker} returned verified evidence.")
        return CommandResponse(
            command="autonomous_result_followup",
            status="healthy",
            message=message,
            data={
                "intent": "recall_verified_autonomous_result",
                "worker": worker,
                "executive_result": context.get("executive_result"),
                "external_action_taken": False,
            },
        )

    def _recommend_from_last_verified_result(self) -> CommandResponse:
        context = dict(self._last_verified_result or {})
        worker = str(context.get("worker") or "the worker").strip()
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        proposal = self._first_rendered(evidence, ("recommended_next_action", "next_action", "recommendation"))
        result = self._best_result_text(evidence)
        if proposal:
            message = (
                f"Based on the verified {worker} result, the next proposed move is: {proposal} "
                "I would use that as the working recommendation, while keeping any consequential send or persisted change behind the existing approval boundary."
            )
        elif result:
            message = (
                f"The verified result is: {result} "
                "There is not enough grounded next-action evidence in the return itself for me to invent a consequential move. "
                "I would re-rank the current agency priorities against this evidence before acting."
            )
        else:
            message = (
                f"{worker} returned verified evidence, but not enough decision-grade content for a grounded recommendation. "
                "I would reassess the current agency priorities rather than manufacture a next step."
            )
        return CommandResponse(
            command="autonomous_result_recommendation",
            status="healthy",
            message=message,
            data={
                "intent": "recommend_from_verified_autonomous_result",
                "worker": worker,
                "proposed_next_action": proposal,
                "external_action_taken": False,
            },
        )

    @classmethod
    def _matches_follow_up(cls, lowered: str, markers: tuple[str, ...]) -> bool:
        candidate = lowered.strip().rstrip("?!.,")
        for prefix in cls._ACKNOWLEDGEMENT_PREFIXES:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].strip().rstrip("?!.,")
                break
        return any(candidate == marker or candidate.startswith(marker + " ") for marker in markers)

    @classmethod
    def _best_result_text(cls, evidence: dict[str, Any]) -> str:
        return cls._first_rendered(evidence, cls._EXECUTIVE_RESULT_KEYS)

    @classmethod
    def _first_rendered(cls, evidence: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            rendered = cls._render_result_value(evidence.get(key))
            if rendered:
                return rendered
        return ""

    @classmethod
    def _verify_evidence(cls, dispatch: dict[str, Any], evidence: Any) -> tuple[bool, str]:
        if not isinstance(evidence, dict) or not evidence:
            return False, "no structured evidence returned"
        if evidence.get("ok") is False or evidence.get("verified") is False or evidence.get("error"):
            return False, "worker reported an error or unverified result"

        mode = str(dispatch.get("execution_mode") or "").strip()
        if mode == "autonomous_read":
            read_only = evidence.get("read_only") is True or evidence.get("mutation_count") == 0
            if not read_only:
                return False, "read-only execution was not demonstrated"
            if not cls._has_source_identifier(evidence):
                return False, "source identifiers are missing"
            if cls._requires_decision_grade_read(dispatch) and not cls._has_work_product(evidence):
                return False, "decision-grade commercial read content is missing"
            return True, "verified read evidence"

        if mode == "autonomous_prepare":
            if not cls._has_work_product(evidence):
                return False, "returned work product is missing"
            return True, "verified internal work product"

        if mode == "approval_gated_write":
            if dispatch.get("approval_granted") is not True or dispatch.get("state") != "approved_pending_execution":
                return False, "explicit scoped approval is missing"
            if not cls._has_write_proof(evidence):
                return False, "write execution proof is missing"
            if not cls._has_source_identifier(evidence):
                return False, "write result identifiers are missing"
            return True, "verified approved write evidence"

        return False, "dispatch execution mode is missing or unsupported"

    @classmethod
    def _executive_result_summary(
        cls,
        worker: str,
        dispatch: dict[str, Any],
        evidence: dict[str, Any],
    ) -> str:
        """Turn verified worker evidence into a concise executive-facing result."""
        for key in cls._EXECUTIVE_RESULT_KEYS:
            value = evidence.get(key)
            rendered = cls._render_result_value(value)
            if rendered:
                return f"{worker} completed the step. {rendered}"

        mode = str(dispatch.get("execution_mode") or "").strip()
        if mode == "autonomous_read":
            return f"{worker} completed the read-only check and returned verified source evidence."
        if mode == "approval_gated_write":
            return f"{worker} completed the approved action and returned verified execution evidence."
        return f"{worker} completed the internal preparation step and returned verified work for review."

    @classmethod
    def _render_result_value(cls, value: Any) -> str:
        if isinstance(value, str):
            text = " ".join(value.split()).strip()
            if not text:
                return ""
            return text if len(text) <= 600 else text[:597].rstrip() + "..."
        if isinstance(value, (list, tuple)):
            items = [cls._render_result_value(item) for item in value[:3]]
            items = [item for item in items if item]
            return "; ".join(items)
        if isinstance(value, dict):
            for key in ("summary", "recommendation", "content", "result", "title"):
                rendered = cls._render_result_value(value.get(key))
                if rendered:
                    return rendered
        return ""

    @classmethod
    def _has_source_identifier(cls, evidence: dict[str, Any]) -> bool:
        return any(cls._meaningful(evidence.get(key)) for key in cls._SOURCE_ID_KEYS)

    @classmethod
    def _requires_decision_grade_read(cls, dispatch: dict[str, Any]) -> bool:
        worker = str(dispatch.get("worker") or "").strip().casefold()
        if worker != "gmail":
            return False
        action = str(dispatch.get("action") or dispatch.get("instruction") or "").strip().casefold()
        return any(marker in action for marker in ("reply", "email thread", "commercial", "lead"))

    @classmethod
    def _has_work_product(cls, evidence: dict[str, Any]) -> bool:
        return any(cls._meaningful(evidence.get(key)) for key in cls._WORK_PRODUCT_KEYS)

    @classmethod
    def _has_write_proof(cls, evidence: dict[str, Any]) -> bool:
        for key in cls._WRITE_PROOF_KEYS:
            value = evidence.get(key)
            if key == "mutation_count":
                if isinstance(value, (int, float)) and value > 0:
                    return True
                continue
            if value is True:
                return True
        return False

    @staticmethod
    def _meaningful(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    @staticmethod
    def _with_dispatch_state(
        response: CommandResponse,
        data: dict[str, Any],
        handoff: dict[str, Any],
        dispatch: dict[str, Any],
        *,
        state: str,
        execution_truth: str,
        message_suffix: str,
    ) -> CommandResponse:
        updated_dispatch = dict(dispatch)
        updated_dispatch["state"] = state
        updated_dispatch["execution_truth"] = execution_truth
        updated_handoff = dict(handoff)
        updated_handoff["dispatch"] = updated_dispatch
        updated_handoff["execution_truth"] = execution_truth
        updated_data = dict(data)
        updated_data["execution_handoff"] = updated_handoff
        updated_data["autonomous_dispatch_state"] = state
        return CommandResponse(
            command=response.command,
            status=response.status,
            message=response.message + message_suffix,
            data=updated_data,
        )
