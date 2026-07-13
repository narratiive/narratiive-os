from __future__ import annotations

from collections.abc import Iterable

from .models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus


class InvalidTransition(ValueError):
    """Raised when a workflow transition violates the runtime contract."""


_ALLOWED_TRANSITIONS: dict[StageStatus, set[StageStatus]] = {
    StageStatus.NOT_STARTED: {StageStatus.READY, StageStatus.BLOCKED},
    StageStatus.READY: {StageStatus.RUNNING, StageStatus.BLOCKED},
    StageStatus.RUNNING: {
        StageStatus.COMPLETED,
        StageStatus.BLOCKED,
        StageStatus.RETRY_REQUIRED,
        StageStatus.REVISION_REQUIRED,
        StageStatus.FAILED,
    },
    StageStatus.BLOCKED: {StageStatus.READY, StageStatus.FAILED},
    StageStatus.RETRY_REQUIRED: {StageStatus.READY, StageStatus.BLOCKED, StageStatus.FAILED},
    StageStatus.REVISION_REQUIRED: {StageStatus.READY, StageStatus.BLOCKED, StageStatus.FAILED},
    StageStatus.COMPLETED: {StageStatus.REVISION_REQUIRED},
    StageStatus.FAILED: set(),
}


class WorkflowEngine:
    """Pure state transition engine. It performs no network or model calls."""

    def initialise(self, state: WorkflowState, available_inputs: Iterable[str]) -> WorkflowState:
        if not state.stages:
            raise ValueError("workflow must define at least one stage")
        self._evaluate_readiness(state, state.stages[0], set(available_inputs))
        self._refresh_workflow(state)
        return state

    def start_stage(self, state: WorkflowState, stage_id: str) -> WorkflowState:
        stage = state.stage(stage_id)
        self._require_current(state, stage)
        self._transition(stage, StageStatus.RUNNING)
        stage.mark_started()
        stage.failure_reason = None
        stage.missing_inputs.clear()
        state.touch()
        return state

    def complete_stage(
        self,
        state: WorkflowState,
        stage_id: str,
        outputs: Iterable[ArtifactRef],
        next_available_inputs: Iterable[str] = (),
    ) -> WorkflowState:
        stage = state.stage(stage_id)
        self._require_current(state, stage)
        output_list = list(outputs)
        if not output_list:
            raise InvalidTransition("a completed stage must produce at least one artifact")
        self._transition(stage, StageStatus.COMPLETED)
        stage.output_artifacts = output_list
        stage.mark_completed()

        index = state.stages.index(stage)
        if index + 1 < len(state.stages):
            next_stage = state.stages[index + 1]
            next_stage.input_artifacts = output_list.copy()
            self._evaluate_readiness(state, next_stage, set(next_available_inputs))
        else:
            state.current_stage_id = None
            state.status = (
                WorkflowStatus.AWAITING_APPROVAL
                if state.approval_required
                else WorkflowStatus.COMPLETE
            )
        self._refresh_workflow(state)
        return state

    def block_stage(self, state: WorkflowState, stage_id: str, missing_inputs: Iterable[str]) -> WorkflowState:
        stage = state.stage(stage_id)
        missing = sorted({item.strip() for item in missing_inputs if item.strip()})
        if not missing:
            raise ValueError("blocked stage must identify missing inputs")
        self._transition(stage, StageStatus.BLOCKED)
        stage.missing_inputs = missing
        stage.failure_reason = "missing required inputs"
        self._refresh_workflow(state)
        return state

    def request_retry(self, state: WorkflowState, stage_id: str, reason: str) -> WorkflowState:
        stage = state.stage(stage_id)
        self._require_current(state, stage)
        self._transition(stage, StageStatus.RETRY_REQUIRED)
        stage.retry_count += 1
        stage.failure_reason = reason.strip() or "recoverable stage failure"
        self._refresh_workflow(state)
        return state

    def request_revision(self, state: WorkflowState, stage_id: str, owner_stage_id: str, reason: str) -> WorkflowState:
        stage = state.stage(stage_id)
        owner = state.stage(owner_stage_id)
        if state.stages.index(owner) > state.stages.index(stage):
            raise InvalidTransition("revision owner must be the same stage or an upstream stage")
        self._transition(stage, StageStatus.REVISION_REQUIRED)
        owner.status = StageStatus.REVISION_REQUIRED
        owner.failure_reason = reason.strip() or "revision requested"
        state.current_stage_id = owner.stage_id
        state.revision_owner = owner.stage_id
        self._refresh_workflow(state)
        return state

    def resume_stage(self, state: WorkflowState, stage_id: str, available_inputs: Iterable[str]) -> WorkflowState:
        stage = state.stage(stage_id)
        if stage.status not in {StageStatus.BLOCKED, StageStatus.RETRY_REQUIRED, StageStatus.REVISION_REQUIRED}:
            raise InvalidTransition(f"cannot resume stage from {stage.status.value}")
        self._evaluate_readiness(state, stage, set(available_inputs))
        self._refresh_workflow(state)
        return state

    def _evaluate_readiness(self, state: WorkflowState, stage: StageRecord, available_inputs: set[str]) -> None:
        missing = sorted(set(stage.required_inputs) - available_inputs)
        target = StageStatus.BLOCKED if missing else StageStatus.READY
        self._transition(stage, target)
        stage.missing_inputs = missing
        stage.failure_reason = "missing required inputs" if missing else None
        state.current_stage_id = stage.stage_id

    @staticmethod
    def _require_current(state: WorkflowState, stage: StageRecord) -> None:
        if state.current_stage_id != stage.stage_id:
            raise InvalidTransition(f"{stage.stage_id} is not the current stage")

    @staticmethod
    def _transition(stage: StageRecord, target: StageStatus) -> None:
        if target == stage.status:
            return
        if target not in _ALLOWED_TRANSITIONS[stage.status]:
            raise InvalidTransition(f"invalid transition: {stage.status.value} -> {target.value}")
        stage.status = target

    @staticmethod
    def _refresh_workflow(state: WorkflowState) -> None:
        if state.status in {
            WorkflowStatus.COMPLETE,
            WorkflowStatus.AWAITING_APPROVAL,
        }:
            state.touch()
            return
        current = state.stage(state.current_stage_id) if state.current_stage_id else None
        if current and current.status == StageStatus.BLOCKED:
            state.status = WorkflowStatus.BLOCKED
        elif current and current.status == StageStatus.FAILED:
            state.status = WorkflowStatus.FAILED
        else:
            state.status = WorkflowStatus.ACTIVE
        state.touch()
