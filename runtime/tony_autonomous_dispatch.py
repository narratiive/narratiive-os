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
    """Execute only explicitly eligible autonomous dispatch contracts.

    This layer is deliberately narrow. It never decides that an action is safe; it
    consumes the risk decision already made upstream. Approval-gated writes remain
    untouched. A dispatcher must return structured evidence that satisfies the
    dispatch contract before Tony can say a read or preparation step actually ran.
    Verified work is then summarised into Tony's visible reply so autonomous work
    advances the conversation instead of merely exposing raw worker evidence.
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

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
    ) -> None:
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
        return self._dispatch_if_eligible(response)

    def _dispatch_if_eligible(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        handoff = data.get("execution_handoff")
        if not isinstance(handoff, dict):
            return response
        dispatch = handoff.get("dispatch")
        if not isinstance(dispatch, dict) or not bool(dispatch.get("eligible")):
            return response
        if dispatch.get("state") != "ready_for_autonomous_dispatch":
            return response
        if dispatch.get("execution_truth") != "not_dispatched":
            return response

        worker = str(dispatch.get("worker") or "").strip()
        handler = self.dispatchers.get(worker)
        if handler is None:
            return self._with_dispatch_state(
                response,
                data,
                handoff,
                dispatch,
                state="dispatcher_unavailable",
                execution_truth="not_dispatched",
                message_suffix=f" I could not dispatch the safe {worker or 'worker'} step because no live dispatcher is configured.",
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
                message_suffix=f" I attempted the safe {worker} step, but it did not return verified evidence: {exc}",
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
                    f" I attempted the safe {worker} step, but the returned evidence did not satisfy the dispatch contract"
                    f" ({reason}), so I am not treating it as complete."
                ),
            )

        result = DispatchResult(worker=worker, status="verified", evidence=evidence)
        executive_result = self._executive_result_summary(worker, dispatch, evidence)
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
        updated.data["execution_status"] = "autonomous_step_verified"
        updated.data["executive_result"] = executive_result
        return updated

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
            return True, "verified read evidence"

        if mode == "autonomous_prepare":
            if not cls._has_work_product(evidence):
                return False, "returned work product is missing"
            return True, "verified internal work product"

        return False, "dispatch execution mode is missing or not autonomous"

    @classmethod
    def _executive_result_summary(
        cls,
        worker: str,
        dispatch: dict[str, Any],
        evidence: dict[str, Any],
    ) -> str:
        """Turn verified worker evidence into a concise executive-facing result.

        Raw source identifiers remain in structured data for auditability, but Tony's
        visible response should communicate the useful result rather than implementation
        plumbing. Workers are encouraged to return `summary` or `recommendation`; the
        fallback remains truthful when the contract proves execution but no narrative
        result was supplied.
        """
        for key in cls._EXECUTIVE_RESULT_KEYS:
            value = evidence.get(key)
            rendered = cls._render_result_value(value)
            if rendered:
                return f"{worker} completed the safe step. {rendered}"

        mode = str(dispatch.get("execution_mode") or "").strip()
        if mode == "autonomous_read":
            return f"{worker} completed the read-only check and returned verified source evidence."
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
    def _has_work_product(cls, evidence: dict[str, Any]) -> bool:
        return any(cls._meaningful(evidence.get(key)) for key in cls._WORK_PRODUCT_KEYS)

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
