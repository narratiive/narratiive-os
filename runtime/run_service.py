from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from .definitions import WorkflowDefinition
from .models import ArtifactRef, WorkflowState, WorkflowStatus
from .repositories import EventLog, WorkflowEvent, WorkflowRunRepository
from .state_machine import WorkflowEngine


class WorkflowRunService:
    """Application service joining definitions, transitions, snapshots and events."""

    def __init__(
        self,
        repository: WorkflowRunRepository,
        event_log: EventLog,
        engine: WorkflowEngine | None = None,
        workspace_id: str = "legacy",
        client_id: str = "legacy",
    ) -> None:
        self.repository = repository
        self.event_log = event_log
        self.engine = engine or WorkflowEngine()
        self.workspace_id = workspace_id
        self.client_id = client_id

    def create_run(
        self,
        definition: WorkflowDefinition,
        run_id: str,
        available_inputs: Iterable[str],
    ) -> WorkflowState:
        if self.repository.exists(run_id):
            raise ValueError(f"workflow run already exists: {run_id}")
        state = definition.new_state(
            run_id,
            workspace_id=self.workspace_id,
            client_id=self.client_id,
        )
        self.engine.initialise(state, available_inputs)
        self._commit(
            state,
            "workflow.created",
            {
                "workflow_id": definition.workflow_id,
                "current_stage_id": state.current_stage_id,
                "status": state.status.value,
            },
        )
        return state

    def load_run(self, run_id: str) -> WorkflowState:
        return self.repository.load(run_id)

    def start_stage(self, run_id: str, stage_id: str) -> WorkflowState:
        state = self.repository.load(run_id)
        self.engine.start_stage(state, stage_id)
        self._commit(state, "stage.started", {"stage_id": stage_id})
        return state

    def complete_stage(
        self,
        run_id: str,
        stage_id: str,
        outputs: Iterable[ArtifactRef],
        next_available_inputs: Iterable[str] = (),
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        output_list = list(outputs)
        self.engine.complete_stage(state, stage_id, output_list, next_available_inputs)
        self._commit(
            state,
            "stage.completed",
            {
                "stage_id": stage_id,
                "output_artifact_ids": [item.artifact_id for item in output_list],
                "next_stage_id": state.current_stage_id,
                "workflow_status": state.status.value,
            },
        )
        if state.status == WorkflowStatus.AWAITING_APPROVAL:
            approval_id = (
                f"approval-{state.run_id}-"
                f"{state.stage(stage_id).revision_count}"
            )
            self.event_log.append(
                WorkflowEvent.create(
                    event_id=f"evt-{uuid4().hex}",
                    run_id=state.run_id,
                    event_type="approval.requested",
                    payload={
                        "approval_id": approval_id,
                        "stage_id": stage_id,
                        "artifact_ids": [
                            item.artifact_id for item in output_list
                        ],
                    },
                    workspace_id=state.workspace_id,
                )
            )
        return state

    def block_stage(self, run_id: str, stage_id: str, missing_inputs: Iterable[str]) -> WorkflowState:
        state = self.repository.load(run_id)
        missing = list(missing_inputs)
        self.engine.block_stage(state, stage_id, missing)
        self._commit(state, "stage.blocked", {"stage_id": stage_id, "missing_inputs": missing})
        return state

    def request_retry(self, run_id: str, stage_id: str, reason: str) -> WorkflowState:
        state = self.repository.load(run_id)
        self.engine.request_retry(state, stage_id, reason)
        self._commit(
            state,
            "stage.retry_requested",
            {
                "stage_id": stage_id,
                "reason": reason,
                "retry_count": state.stage(stage_id).retry_count,
            },
        )
        return state

    def request_revision(
        self,
        run_id: str,
        stage_id: str,
        owner_stage_id: str,
        reason: str,
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        self.engine.request_revision(state, stage_id, owner_stage_id, reason)
        self._commit(
            state,
            "stage.revision_requested",
            {
                "stage_id": stage_id,
                "owner_stage_id": owner_stage_id,
                "reason": reason,
            },
        )
        return state

    def resume_stage(
        self,
        run_id: str,
        stage_id: str,
        available_inputs: Iterable[str],
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        available = list(available_inputs)
        self.engine.resume_stage(state, stage_id, available)
        self._commit(
            state,
            "stage.resumed",
            {
                "stage_id": stage_id,
                "status": state.stage(stage_id).status.value,
                "available_inputs": available,
            },
        )
        return state

    def _commit(self, state: WorkflowState, event_type: str, payload: dict[str, object]) -> None:
        self.repository.save(state)
        self.event_log.append(
            WorkflowEvent.create(
                event_id=f"evt-{uuid4().hex}",
                run_id=state.run_id,
                event_type=event_type,
                payload=payload,
                workspace_id=state.workspace_id,
            )
        )
