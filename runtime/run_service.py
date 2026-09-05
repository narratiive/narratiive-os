from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from uuid import uuid4

from .definitions import WorkflowDefinition
from .models import ArtifactRef, StageStatus, WorkflowState, WorkflowStatus
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
        *,
        entity_id: str = "",
        correlation_id: str = "",
        input_payload: Mapping[str, object] | None = None,
    ) -> WorkflowState:
        if self.repository.exists(run_id):
            raise ValueError(f"workflow run already exists: {run_id}")
        state = definition.new_state(
            run_id,
            workspace_id=self.workspace_id,
            client_id=self.client_id,
        )
        state.entity_id = entity_id.strip()
        state.correlation_id = correlation_id.strip()
        state.input_payload = dict(input_payload or {})
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

    def create_or_load_run(
        self,
        definition: WorkflowDefinition,
        run_id: str,
        available_inputs: Iterable[str],
        **identity: object,
    ) -> WorkflowState:
        if not self.repository.exists(run_id):
            return self.create_run(definition, run_id, available_inputs, **identity)
        state = self.repository.load(run_id)
        if state.workflow_id != definition.workflow_id:
            raise ValueError(f"run {run_id} belongs to another workflow")
        entity_id = str(identity.get("entity_id") or "").strip()
        correlation_id = str(identity.get("correlation_id") or "").strip()
        input_payload = identity.get("input_payload")
        if entity_id and state.entity_id != entity_id:
            raise ValueError(f"run {run_id} belongs to another entity")
        if correlation_id and state.correlation_id != correlation_id:
            raise ValueError(f"run {run_id} belongs to another correlation")
        if input_payload is not None:
            supplied = dict(input_payload)
            if any(key not in state.input_payload or state.input_payload[key] != value for key, value in supplied.items()):
                raise ValueError(f"run {run_id} was already created with different inputs")
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

    def record_attempt(self, run_id: str, stage_id: str, attempt: Mapping[str, object]) -> WorkflowState:
        state = self.repository.load(run_id)
        stage = state.stage(stage_id)
        if stage.status is not StageStatus.RUNNING:
            raise ValueError("workflow attempts can only be recorded for a running step")
        if len(stage.attempts) >= stage.max_attempts:
            raise ValueError("workflow step retry policy exhausted")
        stage.attempts.append(dict(attempt))
        state.touch()
        self._commit(
            state,
            "stage.attempt_recorded",
            {"stage_id": stage_id, "attempt": len(stage.attempts)},
        )
        return state

    def record_quality(self, run_id: str, stage_id: str, quality: Mapping[str, object]) -> WorkflowState:
        state = self.repository.load(run_id)
        stage = state.stage(stage_id)
        if stage.status is not StageStatus.RUNNING:
            raise ValueError("quality can only be recorded for a running step")
        stage.quality_result = dict(quality)
        state.touch()
        self._commit(
            state,
            "stage.quality_recorded",
            {"stage_id": stage_id, "passed": quality.get("passed") is True},
        )
        return state

    def merge_inputs(self, run_id: str, inputs: Mapping[str, object]) -> WorkflowState:
        state = self.repository.load(run_id)
        conflicts = sorted(
            key
            for key, value in inputs.items()
            if key in state.input_payload and state.input_payload[key] != value
        )
        if conflicts:
            raise ValueError(f"workflow output cannot overwrite existing inputs: {','.join(conflicts)}")
        state.input_payload.update(dict(inputs))
        state.touch()
        self._commit(
            state,
            "workflow.inputs_merged",
            {"input_fields": sorted(inputs)},
        )
        return state

    def block_for_reason(self, run_id: str, stage_id: str, blocker: str, next_action: str) -> WorkflowState:
        state = self.repository.load(run_id)
        self.engine.block_for_reason(state, stage_id, blocker, next_action)
        self._commit(
            state,
            "stage.blocked",
            {"stage_id": stage_id, "blocker": blocker, "proposed_next_action": next_action},
        )
        return state

    def pause_for_approval(self, run_id: str, proposed_next_action: str) -> WorkflowState:
        state = self.repository.load(run_id)
        action = proposed_next_action.strip()
        if not action:
            raise ValueError("approval pause requires an exact proposed next action")
        if (
            state.approval_status == "approved"
            and state.approval_history
            and state.approval_history[-1].get("proposed_next_action") == action
        ):
            return state
        state.status = WorkflowStatus.AWAITING_APPROVAL
        state.approval_status = "pending"
        state.proposed_next_action = action
        state.touch()
        self._commit(
            state,
            "approval.requested",
            {"stage_id": state.current_stage_id, "proposed_next_action": action},
        )
        return state

    def approve(self, run_id: str, *, approver: str, rationale: str) -> WorkflowState:
        state = self.repository.load(run_id)
        identity = approver.strip()
        reason = rationale.strip()
        if state.approval_status != "pending" or state.status is not WorkflowStatus.AWAITING_APPROVAL:
            raise ValueError("workflow run is not awaiting approval")
        if not identity or not reason:
            raise ValueError("approval requires approver identity and rationale")
        approval = {
            "approver": identity,
            "rationale": reason,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "proposed_next_action": state.proposed_next_action,
        }
        state.approval_history.append(approval)
        state.approval_status = "approved"
        state.status = WorkflowStatus.ACTIVE if state.current_stage_id else WorkflowStatus.COMPLETE
        state.touch()
        self._commit(state, "approval.granted", approval)
        return state

    def record_external_action(
        self,
        run_id: str,
        *,
        idempotency_key: str,
        receipt: Mapping[str, object],
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        key = idempotency_key.strip()
        if not key or not receipt:
            raise ValueError("external action requires an idempotency key and receipt")
        if any(item.get("idempotency_key") == key for item in state.external_action_receipts):
            return state
        record = {"idempotency_key": key, "receipt": dict(receipt)}
        state.external_action_receipts.append(record)
        state.external_action_taken = True
        state.touch()
        self._commit(state, "external_action.recorded", record)
        return state

    def recover_interrupted_runs(self) -> int:
        recovered = 0
        for run_id in self.repository.list_run_ids():
            state = self.repository.load(run_id)
            if not state.current_stage_id:
                continue
            stage = state.stage(state.current_stage_id)
            if stage.status is not StageStatus.RUNNING:
                continue
            if stage.side_effect_classification == "external_write":
                self.engine.block_for_reason(
                    state,
                    stage.stage_id,
                    "ambiguous_external_action_requires_reconciliation",
                    "Reconcile the external provider using the persisted idempotency key before resuming.",
                )
                self._commit(state, "stage.recovery_blocked", {"stage_id": stage.stage_id})
                recovered += 1
                continue
            self.engine.request_retry(state, stage.stage_id, "recovered_after_runtime_restart")
            self.engine.resume_stage(state, stage.stage_id, stage.required_inputs)
            self._commit(state, "stage.recovered", {"stage_id": stage.stage_id})
            recovered += 1
        return recovered

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
