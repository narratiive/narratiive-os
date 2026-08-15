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
    untouched. A dispatcher must return structured evidence before Tony can say a
    read or preparation step actually ran.
    """

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

        if not isinstance(evidence, dict) or not evidence:
            return self._with_dispatch_state(
                response,
                data,
                handoff,
                dispatch,
                state="dispatch_unverified",
                execution_truth="dispatch_attempted_unverified",
                message_suffix=f" I attempted the safe {worker} step, but no structured evidence came back, so I am not treating it as complete.",
            )

        result = DispatchResult(worker=worker, status="verified", evidence=evidence)
        updated = self._with_dispatch_state(
            response,
            data,
            handoff,
            dispatch,
            state="dispatch_verified",
            execution_truth="verified_dispatch",
            message_suffix=f" The safe {worker} step has now run and returned verified evidence for my review.",
        )
        updated.data["dispatch_result"] = result.to_dict()
        updated.data["execution_status"] = "autonomous_step_verified"
        return updated

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
