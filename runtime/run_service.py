from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
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
        if state.status == WorkflowStatus.AWAITING_APPROVAL:
            state.approval_status = "pending"
            state.proposed_next_action = (
                f"Approve completed {state.workflow_id} work before consequential use or handoff."
            )
            state.touch()
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
                        "proposed_next_action": state.proposed_next_action,
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
        revision_attempts = sum(
            1
            for item in stage.attempts
            if int(item.get("revision", 0)) == stage.revision_count
        )
        if revision_attempts >= stage.max_attempts:
            raise ValueError("workflow step retry policy exhausted")
        recorded_attempt = dict(attempt)
        recorded_attempt.setdefault("revision", stage.revision_count)
        stage.attempts.append(recorded_attempt)
        state.touch()
        self._commit(
            state,
            "stage.attempt_recorded",
            {"stage_id": stage_id, "attempt": len(stage.attempts)},
        )
        return state

    def request_quality_revision(
        self,
        run_id: str,
        *,
        reviewer: str,
        rationale: str,
    ) -> WorkflowState:
        """Explicitly reopen a quality-blocked step as a new bounded revision cycle."""
        return self._request_blocked_revision(
            run_id,
            reviewer=reviewer,
            rationale=rationale,
            allowed_blocker=lambda value: value.startswith("quality_failed:"),
        )

    def request_blocked_revision(
        self,
        run_id: str,
        *,
        reviewer: str,
        rationale: str,
    ) -> WorkflowState:
        """Explicitly reopen revisable worker or quality failures without erasing evidence."""
        return self._request_blocked_revision(
            run_id,
            reviewer=reviewer,
            rationale=rationale,
            allowed_blocker=lambda value: (
                value.startswith("quality_failed:")
                or value == "worker_retry_policy_exhausted"
                or value.startswith("worker_output_rejected:")
            ),
        )

    def _request_blocked_revision(
        self,
        run_id: str,
        *,
        reviewer: str,
        rationale: str,
        allowed_blocker: Callable[[str], bool],
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        identity = reviewer.strip()
        reason = rationale.strip()
        if not identity or not reason:
            raise ValueError("revision requires reviewer identity and rationale")
        if (
            state.status is not WorkflowStatus.BLOCKED
            or not allowed_blocker(str(state.blocker or ""))
            or not state.current_stage_id
        ):
            raise ValueError("workflow run is not blocked by a revisable worker or quality failure")
        stage = state.stage(state.current_stage_id)
        if stage.status is not StageStatus.BLOCKED:
            raise ValueError("blocked workflow step is not revisable")
        stage.revision_count += 1
        revision = {
            "reviewer": identity,
            "rationale": reason,
            "decision": "request_revision",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "stage_id": stage.stage_id,
            "revision_count": stage.revision_count,
        }
        state.approval_history.append(revision)
        self.engine.request_revision(state, stage.stage_id, stage.stage_id, reason)
        self.engine.resume_stage(state, stage.stage_id, state.input_payload.keys())
        self._commit(state, "quality.revision_requested", revision)
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

    def promote_stage_outputs(
        self,
        run_id: str,
        stage_id: str,
        outputs: Mapping[str, object],
    ) -> WorkflowState:
        """Promote validated stage outputs into the run's current derived view.

        Initial execution retains the strict no-overwrite input contract.  A
        formally requested revision may replace only fields declared as outputs
        of the same previously completed stage.  Prior artefacts and events stay
        immutable and remain the audit history for the replaced view.
        """
        state = self.repository.load(run_id)
        stage = state.stage(stage_id)
        output_fields = set(outputs)
        if not output_fields.issubset(set(stage.expected_outputs)):
            raise ValueError("stage output promotion contains undeclared fields")
        conflicts = sorted(
            key
            for key, value in outputs.items()
            if key in state.input_payload and state.input_payload[key] != value
        )
        if conflicts and not (
            stage.revision_count > 0
            and stage.output_artifacts
            and set(conflicts).issubset(set(stage.expected_outputs))
        ):
            raise ValueError(f"workflow output cannot overwrite existing inputs: {','.join(conflicts)}")
        state.input_payload.update(dict(outputs))
        state.touch()
        self._commit(
            state,
            "workflow.outputs_promoted",
            {
                "stage_id": stage_id,
                "output_fields": sorted(outputs),
                "revision_count": stage.revision_count,
            },
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
            state.status is WorkflowStatus.AWAITING_APPROVAL
            and state.approval_status == "pending"
            and state.proposed_next_action == action
        ):
            return state
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

    def approve(
        self,
        run_id: str,
        *,
        approver: str,
        rationale: str,
        approval_binding: Mapping[str, object] | None = None,
    ) -> WorkflowState:
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
        if approval_binding:
            approval["approval_binding"] = dict(approval_binding)
        state.approval_history.append(approval)
        state.approval_status = "approved"
        state.proposed_next_action = None
        state.status = WorkflowStatus.ACTIVE if state.current_stage_id else WorkflowStatus.COMPLETE
        state.touch()
        self._commit(state, "approval.granted", approval)
        return state

    def reject_for_revision(
        self,
        run_id: str,
        *,
        reviewer: str,
        rationale: str,
        approval_binding: Mapping[str, object] | None = None,
    ) -> WorkflowState:
        """Record an explicit rejection and reopen the producing step.

        The completed artefact and prior approval request remain immutable.  A
        revision creates another attempt/version; it never rewrites the output
        that was reviewed.
        """
        state = self.repository.load(run_id)
        identity = reviewer.strip()
        reason = rationale.strip()
        if state.approval_status != "pending" or state.status is not WorkflowStatus.AWAITING_APPROVAL:
            raise ValueError("workflow run is not awaiting approval")
        if not identity or not reason:
            raise ValueError("rejection requires reviewer identity and rationale")
        completed = [stage for stage in state.stages if stage.status is StageStatus.COMPLETED]
        if not completed:
            raise ValueError("workflow run has no completed step to revise")
        owner = completed[-1]
        rejection = {
            "reviewer": identity,
            "rationale": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "proposed_next_action": state.proposed_next_action,
        }
        if approval_binding:
            rejection["approval_binding"] = dict(approval_binding)
        state.approval_history.append(rejection)
        state.approval_status = "rejected"
        state.status = WorkflowStatus.ACTIVE
        state.proposed_next_action = None
        state.blocker = None
        self.engine.request_revision(state, owner.stage_id, owner.stage_id, reason)
        owner.revision_count += 1
        self.engine.resume_stage(state, owner.stage_id, state.input_payload.keys())
        self._commit(
            state,
            "approval.revision_requested",
            {**rejection, "stage_id": owner.stage_id, "revision_count": owner.revision_count},
        )
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

    def record_campaign_world_selection(
        self,
        run_id: str,
        *,
        approver: str,
        rationale: str,
        candidate_id: str,
        candidate_checksum: str,
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        if state.workflow_id != "growth_blueprint_to_campaign_world":
            raise ValueError("Campaign World selection belongs to the Campaign World workflow")
        if state.status is not WorkflowStatus.COMPLETE or state.approval_status != "approved":
            raise ValueError("Campaign World selection requires an approved completed review gate")
        if "matt" not in {token for token in re.split(r"[^a-z0-9]+", approver.strip().casefold()) if token}:
            raise ValueError("Campaign World selection requires Matt's authenticated identity")
        decision = {
            "decision": "campaign_world_selection",
            "approver": approver.strip(),
            "rationale": rationale.strip(),
            "candidate_id": candidate_id.strip(),
            "candidate_checksum": candidate_checksum.strip(),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        if any(not decision[key] for key in ("approver", "rationale", "candidate_id", "candidate_checksum")):
            raise ValueError("Campaign World selection requires exact candidate approval evidence")
        existing = [item for item in state.approval_history if item.get("decision") == "campaign_world_selection"]
        if existing:
            prior = existing[-1]
            if prior.get("candidate_id") == decision["candidate_id"] and prior.get("candidate_checksum") == decision["candidate_checksum"]:
                return state
            raise ValueError("a different Campaign World has already been selected")
        state.approval_history.append(decision)
        state.touch()
        self._commit(state, "campaign_world.selected", decision)
        return state

    def record_creative_bible_approval(
        self,
        run_id: str,
        *,
        approver: str,
        rationale: str,
        creative_bible_checksum: str,
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        if state.workflow_id != "campaign_world_to_creative_bible":
            raise ValueError("Creative Bible approval belongs to the Creative Bible workflow")
        if state.status is not WorkflowStatus.COMPLETE or state.approval_status != "approved":
            raise ValueError("Creative Bible approval requires an approved completed Tony review gate")
        if "matt" not in {token for token in re.split(r"[^a-z0-9]+", approver.strip().casefold()) if token}:
            raise ValueError("Creative Director's Bible approval requires Matt's authenticated identity")
        decision = {
            "decision": "creative_bible_approval",
            "approver": approver.strip(),
            "rationale": rationale.strip(),
            "creative_bible_checksum": creative_bible_checksum.strip(),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        if any(not decision[key] for key in ("approver", "rationale", "creative_bible_checksum")):
            raise ValueError("Creative Bible approval requires exact-version approval evidence")
        existing = [item for item in state.approval_history if item.get("decision") == "creative_bible_approval"]
        if existing:
            prior = existing[-1]
            if prior.get("creative_bible_checksum") == decision["creative_bible_checksum"]:
                return state
            raise ValueError("a different Creative Director's Bible version has already been approved")
        state.approval_history.append(decision)
        state.touch()
        self._commit(state, "creative_bible.approved", decision)
        return state

    def record_asset_suite_approval(
        self,
        run_id: str,
        *,
        approver: str,
        rationale: str,
        asset_suite_checksum: str,
        asset_version_ids: Iterable[str],
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        if state.workflow_id != "creative_bible_to_asset_production":
            raise ValueError("asset-suite approval belongs to the asset-production workflow")
        if state.status is not WorkflowStatus.COMPLETE or state.approval_status != "approved":
            raise ValueError("asset-suite approval requires a completed approved production review gate")
        if "matt" not in {token for token in re.split(r"[^a-z0-9]+", approver.strip().casefold()) if token}:
            raise ValueError("asset-suite approval requires Matt's authenticated identity")
        version_ids = tuple(str(item).strip() for item in asset_version_ids if str(item).strip())
        if not version_ids or len(version_ids) != len(set(version_ids)):
            raise ValueError("asset-suite approval requires unique exact asset version IDs")
        decision = {
            "decision": "asset_suite_approval",
            "approver": approver.strip(),
            "rationale": rationale.strip(),
            "asset_suite_checksum": asset_suite_checksum.strip(),
            "asset_version_ids": list(version_ids),
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        if any(not decision[key] for key in ("approver", "rationale", "asset_suite_checksum")):
            raise ValueError("asset-suite approval requires exact-version approval evidence")
        existing = [item for item in state.approval_history if item.get("decision") == "asset_suite_approval"]
        if existing:
            prior = existing[-1]
            if prior.get("asset_suite_checksum") == decision["asset_suite_checksum"]:
                return state
            raise ValueError("a different asset-suite version has already been approved")
        state.approval_history.append(decision)
        state.touch()
        self._commit(state, "asset_suite.approved", decision)
        return state

    def record_handoff(
        self,
        run_id: str,
        *,
        next_workflow_id: str,
        next_run_id: str,
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        self._commit(
            state,
            "workflow.handoff_created",
            {
                "next_workflow_id": next_workflow_id,
                "next_run_id": next_run_id,
                "source_artifact_ids": [
                    artifact.artifact_id
                    for stage in state.stages
                    for artifact in stage.output_artifacts
                ],
            },
        )
        return state

    def record_commission(
        self,
        run_id: str,
        *,
        source_run_id: str,
        target_workflow_id: str,
        commitment_id: str,
    ) -> WorkflowState:
        """Record a durable conversational commitment without executing it inline."""

        state = self.repository.load(run_id)
        payload = {
            "source_run_id": source_run_id.strip(),
            "target_workflow_id": target_workflow_id.strip(),
            "commitment_id": commitment_id.strip(),
        }
        if not all(payload.values()):
            raise ValueError("workflow commission requires source, target and commitment identity")
        self._commit(state, "workflow.commissioned", payload)
        return state

    def begin_promised_delivery(self, run_id: str, *, delivery_key: str, kind: str) -> WorkflowState:
        state = self.repository.load(run_id)
        key = delivery_key.strip()
        if not key or not kind.strip():
            raise ValueError("promised delivery requires key and kind")
        existing = state.promised_work_delivery
        if existing:
            if existing.get("delivery_key") != key:
                raise ValueError("a different promised-work delivery is already recorded")
            return state
        state.promised_work_delivery = {
            "delivery_key": key,
            "kind": kind.strip(),
            "status": "attempting",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "evidence": {},
        }
        state.touch()
        self._commit(state, "promised_work.delivery_started", dict(state.promised_work_delivery))
        return state

    def finish_promised_delivery(
        self,
        run_id: str,
        *,
        delivery_key: str,
        evidence: Mapping[str, object],
    ) -> WorkflowState:
        state = self.repository.load(run_id)
        current = state.promised_work_delivery
        if current.get("delivery_key") != delivery_key.strip() or current.get("status") != "attempting":
            raise ValueError("promised-work delivery intent does not match")
        state.promised_work_delivery = {
            **current,
            "status": "delivered",
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "evidence": dict(evidence),
        }
        state.external_action_taken = True
        state.touch()
        self._commit(state, "promised_work.delivered", dict(state.promised_work_delivery))
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
