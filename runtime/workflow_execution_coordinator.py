from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.autonomy_planner import AutonomyAction, TonyAutonomyPlanner
from runtime.client_lifecycle import ClientLifecycleRecord
from runtime.models import ArtifactRef, StageStatus, WorkflowState, WorkflowStatus
from runtime.run_service import WorkflowRunService
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    MalformedWorkerOutput,
    NoAvailableWorker,
    ProhibitedWorkerSideEffect,
)
from runtime.workflow_registry import WorkflowRegistry


QualityValidator = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    run_id: str
    workflow_id: str
    status: str
    action: str
    blocker: str = ""
    proposed_next_action: str = ""
    next_run_id: str = ""
    external_action_taken: bool = False


class FileWorkflowArtifactStore:
    """Immutable JSON work products for generic workflow execution."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def persist(self, state: WorkflowState, stage_id: str, output: Mapping[str, Any]) -> ArtifactRef:
        encoded = json.dumps(dict(output), sort_keys=True, separators=(",", ":")).encode("utf-8")
        checksum = hashlib.sha256(encoded).hexdigest()
        identity = hashlib.sha256(f"{state.run_id}:{stage_id}".encode("utf-8")).hexdigest()
        artifact_id = f"artifact-{identity[:16]}-{checksum[:16]}"
        target = self.root / f"{artifact_id}.json"
        if target.exists():
            if target.read_bytes() != encoded + b"\n":
                raise ValueError("immutable workflow artifact collision")
        else:
            fd, temporary = tempfile.mkstemp(prefix=f".{artifact_id}.", suffix=".tmp", dir=self.root)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(encoded)
                    handle.write(b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_type="workflow_step_output",
            location=str(target),
            checksum=checksum,
            metadata={
                "workflow_id": state.workflow_id,
                "stage_id": stage_id,
                "parent_artifact_ids": list(
                    state.input_payload.get("_lineage", {}).get("parent_artifact_ids", ())
                ) if isinstance(state.input_payload.get("_lineage"), Mapping) else [],
            },
        )


class WorkflowExecutionCoordinator:
    """Drive durable workflow progression from planner decisions and contracts."""

    def __init__(
        self,
        *,
        registry: WorkflowRegistry,
        workers: CapabilityWorkerRegistry,
        runs: WorkflowRunService,
        artifacts: FileWorkflowArtifactStore,
        quality_validators: Mapping[str, QualityValidator] | None = None,
        planner: TonyAutonomyPlanner | None = None,
    ) -> None:
        self.registry = registry
        self.workers = workers
        self.runs = runs
        self.artifacts = artifacts
        self.quality_validators = dict(quality_validators or {})
        self.planner = planner or TonyAutonomyPlanner()
        self.lock_root = self.artifacts.root / ".locks"
        self.lock_root.mkdir(parents=True, exist_ok=True)

    def enqueue(
        self,
        workflow_id: str,
        run_id: str,
        inputs: Mapping[str, Any],
        *,
        entity_id: str,
        correlation_id: str,
    ) -> WorkflowState:
        with self._run_lock(run_id):
            definition = self.registry.resolve(workflow_id)
            return self.runs.create_or_load_run(
                definition,
                run_id,
                inputs.keys(),
                entity_id=entity_id,
                correlation_id=correlation_id,
                input_payload=inputs,
            )

    def approve(self, run_id: str, *, approver: str, rationale: str) -> WorkflowState:
        with self._run_lock(run_id):
            return self.runs.approve(run_id, approver=approver, rationale=rationale)

    def recover_pending(self) -> int:
        return self.runs.recover_interrupted_runs()

    def advance(self, run_id: str, lifecycle: ClientLifecycleRecord) -> ExecutionOutcome:
        with self._run_lock(run_id):
            return self._advance_locked(run_id, lifecycle)

    def _advance_locked(self, run_id: str, lifecycle: ClientLifecycleRecord) -> ExecutionOutcome:
        while True:
            state = self.runs.load_run(run_id)
            if state.client_id != lifecycle.client_id:
                raise ValueError("lifecycle record belongs to a different client")
            if state.status is WorkflowStatus.BLOCKED:
                return self._outcome(state, AutonomyAction.ESCALATE.value)
            if state.status is WorkflowStatus.AWAITING_APPROVAL:
                return self._outcome(state, AutonomyAction.APPROVAL.value)
            if state.status is WorkflowStatus.COMPLETE:
                return self._handoff_or_complete(state, lifecycle)
            if not state.current_stage_id:
                return self._outcome(state, "complete")

            stage = state.stage(state.current_stage_id)
            decision = self.planner.decide(lifecycle)
            if decision.action is AutonomyAction.ESCALATE:
                state = self.runs.block_for_reason(
                    run_id,
                    stage.stage_id,
                    decision.reason,
                    decision.next_action,
                )
                return self._outcome(state, decision.action.value)

            definition = self.registry.resolve(state.workflow_id)
            stage_definition = next(item for item in definition.stages if item.stage_id == stage.stage_id)
            external_action = stage.side_effect_classification == "external_write"
            proposed_action = (
                f"Execute {state.workflow_id}.{stage.stage_id} external action"
                if external_action
                else decision.next_action
            )
            if (decision.action is AutonomyAction.APPROVAL and not self._approval_covers(state, proposed_action)) or (
                external_action and not self._approval_covers(state, proposed_action)
            ):
                state = self.runs.pause_for_approval(run_id, proposed_action)
                return self._outcome(state, AutonomyAction.APPROVAL.value)

            if stage.quality_contract and stage.quality_contract not in self.quality_validators:
                state = self.runs.block_for_reason(
                    run_id,
                    stage.stage_id,
                    f"quality_validator_unavailable:{stage.quality_contract}",
                    "Configure the declared quality validator before worker execution.",
                )
                return self._outcome(state, AutonomyAction.ESCALATE.value)

            try:
                worker = self.workers.resolve(
                    stage.capability,
                    side_effect=stage.side_effect_classification,
                )
            except NoAvailableWorker:
                state = self.runs.block_for_reason(
                    run_id,
                    stage.stage_id,
                    f"worker_unavailable:{stage.capability}",
                    f"Configure an eligible worker for {stage.capability} before resuming.",
                )
                return self._outcome(state, AutonomyAction.ESCALATE.value)

            if stage.status is not StageStatus.READY:
                state = self.runs.block_for_reason(
                    run_id,
                    stage.stage_id,
                    "workflow_step_not_ready",
                    "Resolve the persisted workflow step state before resuming execution.",
                )
                return self._outcome(state, AutonomyAction.ESCALATE.value)

            self.runs.start_stage(run_id, stage.stage_id)
            idempotency_key = f"{state.run_id}:{stage.stage_id}:{len(stage.attempts) + 1}"
            contract = dict(state.input_payload)
            contract["workflow_context"] = {
                "workflow_id": state.workflow_id,
                "run_id": state.run_id,
                "stage_id": stage.stage_id,
                "entity_id": state.entity_id,
                "correlation_id": state.correlation_id,
                "idempotency_key": idempotency_key,
                "side_effect_classification": stage.side_effect_classification,
                "expected_outputs": list(stage.expected_outputs),
                "quality_contract": stage.quality_contract,
            }
            try:
                output = self.workers.execute(
                    worker,
                    contract,
                    side_effect=stage.side_effect_classification,
                    approval_granted=self._approval_covers(state, proposed_action),
                )
            except (MalformedWorkerOutput, ProhibitedWorkerSideEffect) as exc:
                return self._block_failed_attempt(run_id, stage.stage_id, exc)
            except Exception as exc:
                return self._retry_or_block(
                    run_id,
                    stage.stage_id,
                    exc,
                    state.input_payload.keys(),
                    lifecycle,
                )

            self.runs.record_attempt(
                run_id,
                stage.stage_id,
                {
                    "status": "returned",
                    "worker_id": worker.worker_id,
                    "worker_attempt": output.get("worker_execution", {}).get("attempt"),
                },
            )
            missing = [
                field
                for field in stage_definition.output_contract.required_fields
                if field not in output or output[field] in (None, "", [], {})
            ]
            if missing:
                quality = {"passed": False, "failed_checks": [f"required_output:{field}" for field in missing]}
            elif stage.quality_contract:
                validator = self.quality_validators.get(stage.quality_contract)
                try:
                    quality = dict(validator(output))
                    quality["passed"] = quality.get("passed") is True
                except Exception as exc:
                    quality = {
                        "passed": False,
                        "failed_checks": [f"quality_validator_error:{type(exc).__name__}"],
                    }
            else:
                quality = {"passed": True, "failed_checks": []}
            self.runs.record_quality(run_id, stage.stage_id, quality)
            if quality.get("passed") is not True:
                state = self.runs.block_for_reason(
                    run_id,
                    stage.stage_id,
                    f"quality_failed:{stage.quality_contract or 'output_contract'}",
                    "Review the persisted attempt and quality evidence before revision or resume.",
                )
                return self._outcome(state, AutonomyAction.ESCALATE.value)

            if external_action:
                receipt = output.get("external_action_receipt")
                if output.get("external_action_taken") is not True or not isinstance(receipt, Mapping) or not receipt:
                    state = self.runs.block_for_reason(
                        run_id,
                        stage.stage_id,
                        "external_action_receipt_missing",
                        "Reconcile the provider before claiming or retrying the external action.",
                    )
                    return self._outcome(state, AutonomyAction.ESCALATE.value)
                self.runs.record_external_action(
                    run_id,
                    idempotency_key=idempotency_key,
                    receipt=receipt,
                )

            current = self.runs.load_run(run_id)
            artifact = self.artifacts.persist(current, stage.stage_id, output)
            durable_outputs = {
                field: output[field]
                for field in stage_definition.output_contract.required_fields
            }
            self.runs.merge_inputs(run_id, durable_outputs)
            state = self.runs.complete_stage(
                run_id,
                stage.stage_id,
                [artifact],
                durable_outputs.keys(),
            )
            if state.status is WorkflowStatus.AWAITING_APPROVAL or (
                stage.step_approval_required and not external_action
            ):
                state = self.runs.pause_for_approval(
                    run_id,
                    f"Approve completed {state.workflow_id} work before consequential use or handoff.",
                )
                return self._outcome(state, AutonomyAction.APPROVAL.value)

    def _retry_or_block(
        self,
        run_id: str,
        stage_id: str,
        error: Exception,
        available_inputs: Any,
        lifecycle: ClientLifecycleRecord,
    ) -> ExecutionOutcome:
        state = self.runs.load_run(run_id)
        self.runs.record_attempt(
            run_id,
            stage_id,
            {"status": "failed", "error_type": type(error).__name__},
        )
        state = self.runs.load_run(run_id)
        if len(state.stage(stage_id).attempts) < state.stage(stage_id).max_attempts:
            self.runs.request_retry(run_id, stage_id, "worker_execution_failed")
            self.runs.resume_stage(run_id, stage_id, available_inputs)
            return self._advance_locked(run_id, lifecycle)
        state = self.runs.block_for_reason(
            run_id,
            stage_id,
            "worker_retry_policy_exhausted",
            "Inspect attempt evidence and repair or replace the worker before resuming.",
        )
        return self._outcome(state, AutonomyAction.ESCALATE.value)

    def _block_failed_attempt(self, run_id: str, stage_id: str, error: Exception) -> ExecutionOutcome:
        self.runs.record_attempt(
            run_id,
            stage_id,
            {"status": "rejected", "error_type": type(error).__name__},
        )
        state = self.runs.block_for_reason(
            run_id,
            stage_id,
            f"worker_output_rejected:{type(error).__name__}",
            "Inspect the persisted attempt evidence and correct the worker adapter or output.",
        )
        return self._outcome(state, AutonomyAction.ESCALATE.value)

    def _handoff_or_complete(
        self,
        state: WorkflowState,
        lifecycle: ClientLifecycleRecord,
    ) -> ExecutionOutcome:
        definition = self.registry.resolve(state.workflow_id)
        if not definition.next_workflow_id or not definition.autonomous_handoff:
            return self._outcome(state, "complete")
        next_definition = self.registry.resolve(definition.next_workflow_id)
        decision = self.planner.decide(lifecycle)
        if decision.action is not AutonomyAction.CONTINUE:
            state = self.runs.pause_for_approval(
                state.run_id,
                f"Hand off {state.workflow_id} to {next_definition.workflow_id}",
            )
            return self._outcome(state, AutonomyAction.APPROVAL.value)
        next_run_id = f"{state.run_id}-{next_definition.workflow_id}"
        latest = state.stages[-1].output_artifacts[-1]
        output = json.loads(Path(latest.location).read_text(encoding="utf-8"))
        self.enqueue(
            next_definition.workflow_id,
            next_run_id,
            output,
            entity_id=state.entity_id,
            correlation_id=state.correlation_id,
        )
        outcome = self.advance(next_run_id, lifecycle)
        return ExecutionOutcome(
            run_id=state.run_id,
            workflow_id=state.workflow_id,
            status=state.status.value,
            action="continue_autonomously",
            next_run_id=next_run_id,
            external_action_taken=state.external_action_taken or outcome.external_action_taken,
        )

    @staticmethod
    def _approval_covers(state: WorkflowState, proposed_action: str) -> bool:
        return bool(
            state.approval_status == "approved"
            and state.approval_history
            and state.approval_history[-1].get("proposed_next_action") == proposed_action
        )

    @staticmethod
    def _outcome(state: WorkflowState, action: str) -> ExecutionOutcome:
        return ExecutionOutcome(
            run_id=state.run_id,
            workflow_id=state.workflow_id,
            status=state.status.value,
            action=action,
            blocker=state.blocker or "",
            proposed_next_action=state.proposed_next_action or "",
            external_action_taken=state.external_action_taken,
        )

    @contextmanager
    def _run_lock(self, run_id: str):
        identity = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        path = self.lock_root / f"{identity}.lock"
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
