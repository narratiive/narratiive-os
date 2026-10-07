from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.autonomy_planner import AutonomyAction, TonyAutonomyPlanner
from runtime.blueprint_director import BlueprintDirectorCommissionBuilder
from runtime.client_lifecycle import ClientLifecycleRecord
from runtime.models import ArtifactRef, StageStatus, WorkflowState, WorkflowStatus
from runtime.run_service import WorkflowRunService
from runtime.serialization import artifact_to_dict
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    MalformedWorkerOutput,
    NoAvailableWorker,
    ProhibitedWorkerSideEffect,
)
from runtime.workflow_registry import WorkflowRegistry
from runtime.workflow_handoffs import build_next_workflow_inputs
from runtime.workflow_run_identity import downstream_run_id


QualityValidator = Callable[[Mapping[str, Any]], Mapping[str, Any]]


_BOUNDED_STRATEGY_CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "research_to_strategic_synthesis": ("contradictions", "research_gaps", "_lineage"),
    "strategic_synthesis_to_strategy_thesis": ("contradictions_and_gaps", "open_inputs", "_lineage"),
    "strategy_thesis_to_growth_blueprint": ("evidence_and_uncertainty", "_lineage"),
}


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

    def persist(
        self,
        state: WorkflowState,
        stage_id: str,
        output: Mapping[str, Any],
        *,
        governance: Mapping[str, Any] | None = None,
    ) -> ArtifactRef:
        return self._persist(
            state,
            stage_id,
            output,
            artifact_type="workflow_step_output",
            governance=governance,
        )

    def persist_attempt(
        self,
        state: WorkflowState,
        stage_id: str,
        output: Mapping[str, Any],
        attempt_number: int,
        governance: Mapping[str, Any] | None = None,
    ) -> ArtifactRef:
        return self._persist(
            state,
            stage_id,
            output,
            artifact_type="worker_attempt_output",
            discriminator=f"attempt-{attempt_number}",
            governance=governance,
        )

    def _persist(
        self,
        state: WorkflowState,
        stage_id: str,
        output: Mapping[str, Any],
        *,
        artifact_type: str,
        discriminator: str = "accepted",
        governance: Mapping[str, Any] | None = None,
    ) -> ArtifactRef:
        encoded = json.dumps(dict(output), sort_keys=True, separators=(",", ":")).encode("utf-8")
        checksum = hashlib.sha256(encoded).hexdigest()
        identity_source = f"{state.run_id}:{stage_id}"
        if discriminator != "accepted":
            identity_source += f":{discriminator}"
        identity = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()
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
        stage = state.stage(stage_id)
        previous = stage.output_artifacts[-1] if stage.output_artifacts else None
        metadata = {
            "workspace_id": state.workspace_id,
            "client_id": state.client_id,
            "entity_id": state.entity_id,
            "correlation_id": state.correlation_id,
            "workflow_id": state.workflow_id,
            "run_id": state.run_id,
            "stage_id": stage_id,
            "version": stage.revision_count + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parent_artifact_ids": list(
                state.input_payload.get("_lineage", {}).get("parent_artifact_ids", ())
            ) if isinstance(state.input_payload.get("_lineage"), Mapping) else [],
            "supersedes_artifact_id": previous.artifact_id if previous else None,
            "revision_count": stage.revision_count,
            "revision_history": [
                dict(item)
                for item in state.approval_history
                if item.get("decision") == "request_revision" or item.get("rejected_at")
            ],
            **dict(governance or {}),
        }
        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            location=str(target),
            checksum=checksum,
            metadata=metadata,
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
        blueprint_director_commission: BlueprintDirectorCommissionBuilder | None = None,
    ) -> None:
        self.registry = registry
        self.workers = workers
        self.runs = runs
        self.artifacts = artifacts
        self.quality_validators = dict(quality_validators or {})
        self.planner = planner or TonyAutonomyPlanner()
        self.blueprint_director_commission = (
            blueprint_director_commission or BlueprintDirectorCommissionBuilder()
        )
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
            prepared_inputs = dict(inputs)
            if workflow_id == "strategy_thesis_to_growth_blueprint":
                prepared_inputs = self.blueprint_director_commission.enrich(
                    prepared_inputs,
                    workspace_id=self.runs.workspace_id,
                    client_id=self.runs.client_id,
                )
            return self.runs.create_or_load_run(
                definition,
                run_id,
                prepared_inputs.keys(),
                entity_id=entity_id,
                correlation_id=correlation_id,
                input_payload=prepared_inputs,
            )

    def approve(
        self,
        run_id: str,
        *,
        approver: str,
        rationale: str,
        approval_binding: Mapping[str, object] | None = None,
    ) -> WorkflowState:
        with self._run_lock(run_id):
            return self.runs.approve(
                run_id,
                approver=approver,
                rationale=rationale,
                approval_binding=approval_binding,
            )

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

            state = self.runs.reconcile_stage_outputs(
                run_id,
                stage.stage_id,
                stage_definition.output_contract.required_fields,
            )
            stage = state.stage(stage.stage_id)
            self.runs.start_stage(run_id, stage.stage_id)
            idempotency_key = f"{state.run_id}:{stage.stage_id}:{len(stage.attempts) + 1}"
            worker_metadata = worker.registration.metadata
            self.runs.record_dispatch_started(
                run_id,
                stage.stage_id,
                idempotency_key=idempotency_key,
                worker_id=worker_metadata.worker_id,
                provider=worker_metadata.provider,
                model=worker_metadata.model,
                timeout_seconds=worker_metadata.timeout_seconds,
                worker_attempt=1,
            )
            contract = self._worker_contract(state, stage_definition.input_contract.required_fields)
            if stage.revision_count > 0:
                latest_revision = next(
                    (
                        item
                        for item in reversed(state.approval_history)
                        if item.get("decision") == "request_revision"
                        and item.get("owner_stage_id") == stage.stage_id
                    ),
                    {},
                )
                contract["revision_feedback"] = {
                    "revision_count": stage.revision_count,
                    "failed_checks": list((stage.quality_result or {}).get("failed_checks") or []),
                    "reviewer_rationale": str(latest_revision.get("rationale") or ""),
                    "instruction": (
                        "Revise from the supplied authoritative inputs. Correct every failed check without "
                        "inventing evidence, weakening uncertainty, or claiming approval."
                    ),
                }
            contract["workflow_context"] = {
                "workflow_id": state.workflow_id,
                "run_id": state.run_id,
                "stage_id": stage.stage_id,
                "entity_id": state.entity_id,
                "correlation_id": state.correlation_id,
                "workspace_id": state.workspace_id,
                "client_id": state.client_id,
                "idempotency_key": idempotency_key,
                "side_effect_classification": stage.side_effect_classification,
                # The executable registry is authoritative for the current output
                # contract. Persisted runs may predate a compatible contract
                # expansion, so advertising their snapshot here can make the
                # worker omit fields the current validator requires.
                "expected_outputs": list(stage_definition.output_contract.required_fields),
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

            missing = [
                field
                for field in stage_definition.output_contract.required_fields
                if field not in output or output[field] in (None, "")
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
            if stage.quality_contract == "senior_strategist_review_quality_gate":
                identity = state.input_payload.get("blueprint_director_output_identity")
                expected = str(identity.get("checksum") or "") if isinstance(identity, Mapping) else ""
                supplied = str(output.get("reviewed_blueprint_checksum") or "")
                checks = dict(quality.get("checks") or {})
                checks["review_binds_exact_blueprint_checksum"] = bool(expected) and supplied == expected
                quality["checks"] = checks
                quality["failed_checks"] = [
                    label.replace("_", " ") for label, passed in checks.items() if not passed
                ]
                quality["passed"] = all(checks.values())
            attempt_evidence: dict[str, Any] = {
                "status": "returned",
                "worker_id": worker.worker_id,
                "worker_attempt": output.get("worker_execution", {}).get("attempt"),
                "quality_passed": quality.get("passed") is True,
            }
            if quality.get("passed") is not True:
                current = self.runs.load_run(run_id)
                candidate = self.artifacts.persist_attempt(
                    current,
                    stage.stage_id,
                    output,
                    len(current.stage(stage.stage_id).attempts) + 1,
                    governance=self._artifact_governance(
                        current, stage.stage_id, worker, quality, approval_status="blocked"
                    ),
                )
                attempt_evidence["candidate_artifact"] = artifact_to_dict(candidate)
            self.runs.record_attempt(run_id, stage.stage_id, attempt_evidence)
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
            artifact = self.artifacts.persist(
                current,
                stage.stage_id,
                output,
                governance=self._artifact_governance(
                    current,
                    stage.stage_id,
                    worker,
                    quality,
                    approval_status="pending" if current.approval_required else "not_required",
                ),
            )
            derived_inputs: dict[str, Any] = {}
            if current.workflow_id == "strategy_thesis_to_growth_blueprint" and stage.stage_id == "direct_growth_blueprint":
                self.runs.record_stage_artifact_identity(
                    run_id,
                    stage_id=stage.stage_id,
                    input_key="blueprint_director_output_identity",
                    artifact=artifact,
                )
                derived_inputs["blueprint_director_output_identity"] = True
            durable_outputs = {
                field: output[field]
                for field in stage_definition.output_contract.required_fields
            }
            self.runs.promote_stage_outputs(run_id, stage.stage_id, durable_outputs)
            state = self.runs.complete_stage(
                run_id,
                stage.stage_id,
                [artifact],
                (*durable_outputs.keys(), *derived_inputs.keys()),
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
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error_code": _safe_worker_error_code(error),
            },
        )
        state = self.runs.load_run(run_id)
        stage = state.stage(stage_id)
        revision_attempts = sum(
            1
            for item in stage.attempts
            if int(item.get("revision", 0)) == stage.revision_count
        )
        if revision_attempts < stage.max_attempts:
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
            {
                "status": "rejected",
                "error_type": type(error).__name__,
                "error_code": _safe_worker_error_code(error),
            },
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
        next_run_id = downstream_run_id(state.run_id, next_definition.workflow_id)
        latest = next(
            (stage.output_artifacts[-1] for stage in reversed(state.stages) if stage.output_artifacts),
            None,
        )
        if latest is None:
            state = self.runs.record_handoff_blocked(
                state.run_id,
                blocker="handoff_artifact_missing",
                proposed_next_action="Restore the immutable source artefact before retrying the handoff.",
            )
            return self._outcome(state, AutonomyAction.ESCALATE.value)
        output = json.loads(Path(latest.location).read_text(encoding="utf-8"))
        inputs = build_next_workflow_inputs(state, output)
        required = next_definition.stages[0].input_contract.required_fields
        for field in next_definition.stages[0].output_contract.required_fields:
            if field not in required:
                inputs.pop(field, None)
        missing = [field for field in required if field not in inputs or inputs[field] in (None, "", [], {})]
        if missing:
            state = self.runs.record_handoff_blocked(
                state.run_id,
                blocker="handoff_inputs_missing",
                proposed_next_action=f"Supply the required downstream evidence: {','.join(missing)}.",
            )
            return self._outcome(state, AutonomyAction.ESCALATE.value)
        self.enqueue(
            next_definition.workflow_id,
            next_run_id,
            inputs,
            entity_id=state.entity_id,
            correlation_id=state.correlation_id,
        )
        self.runs.record_handoff(
            state.run_id,
            next_workflow_id=next_definition.workflow_id,
            next_run_id=next_run_id,
        )
        outcome = self.advance(next_run_id, lifecycle)
        return ExecutionOutcome(
            run_id=state.run_id,
            workflow_id=state.workflow_id,
            status=outcome.status,
            action=outcome.action if outcome.action != "complete" else "continue_autonomously",
            next_run_id=outcome.next_run_id or next_run_id,
            external_action_taken=state.external_action_taken or outcome.external_action_taken,
        )

    @staticmethod
    def _artifact_governance(
        state: WorkflowState,
        stage_id: str,
        worker: Any,
        quality: Mapping[str, Any],
        *,
        approval_status: str,
    ) -> dict[str, Any]:
        metadata = worker.registration.metadata
        governance = {
            "source_input_fields": sorted(
                key for key in state.input_payload if not key.startswith("_")
            ),
            "generating_specialist": metadata.worker_id,
            "provider": metadata.provider,
            "model": metadata.model,
            "quality_contract": state.stage(stage_id).quality_contract,
            "quality_status": "passed" if quality.get("passed") is True else "failed",
            "quality_checks": dict(quality.get("checks") or {}),
            "quality_failures": list(quality.get("failed_checks") or []),
            "approval_status": approval_status,
            "external_action_taken": state.external_action_taken,
        }
        reviewed = state.input_payload.get("blueprint_director_output_identity")
        if stage_id == "review_growth_blueprint" and isinstance(reviewed, Mapping):
            governance["reviewed_artifact_id"] = str(reviewed.get("artifact_id") or "")
            governance["reviewed_artifact_checksum"] = str(reviewed.get("checksum") or "")
            governance["reviewed_artifact_version"] = int(reviewed.get("version") or 0)
        return governance

    @staticmethod
    def _worker_contract(state: WorkflowState, required_fields: tuple[str, ...]) -> dict[str, Any]:
        """Keep long-form strategy prompts bounded without weakening persisted evidence."""
        optional_fields = _BOUNDED_STRATEGY_CONTEXT_FIELDS.get(state.workflow_id)
        if optional_fields is None:
            return dict(state.input_payload)
        allowed = (*required_fields, *optional_fields)
        return {field: state.input_payload[field] for field in allowed if field in state.input_payload}

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


def _safe_worker_error_code(error: Exception) -> str:
    """Retain actionable failure class without persisting provider or client text."""
    message = str(error).casefold()
    if isinstance(error, TimeoutError) or "timed out" in message or "timeout" in message:
        return "worker_timeout"
    if "truncated" in message or "max_tokens" in message:
        return "worker_output_truncated"
    if "no text work product" in message:
        return "worker_output_empty"
    if "json" in message:
        return "worker_output_invalid_json"
    return "worker_execution_failed"
