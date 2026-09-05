from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.client_lifecycle import ClientLifecycleRecord
from runtime.models import StageStatus, WorkflowState, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.research_workflow_adapter import ResearchWorkflowAdapter
from runtime.run_service import WorkflowRunService
from runtime.serialization import workflow_to_dict
from runtime.tony_blueprint_lite_inbound import TonyInboundBlueprintLiteService
from runtime.tony_dispatch_adapters import build_http_dispatchers
from runtime.worker_registry import WorkerAdapter, build_tony_worker_registry
from runtime.workflow_execution_coordinator import (
    ExecutionOutcome,
    FileWorkflowArtifactStore,
    QualityValidator,
    WorkflowExecutionCoordinator,
)
from runtime.workflow_business_projection import WorkflowBusinessProjectionService
from runtime.workflow_registry import build_narratiive_workflow_registry
from runtime.workflow_quality import (
    discovery_preparation_quality_gate,
    growth_blueprint_quality_gate,
    growth_sprint_proposal_quality_gate,
    research_evidence_quality_gate,
    validate_operational_inputs,
)
from runtime.workflow_handoffs import build_next_workflow_inputs


@dataclass(slots=True)
class TonyWorkflowRuntime:
    """Queryable application surface for one workspace/client execution scope."""

    coordinator: WorkflowExecutionCoordinator
    runs: WorkflowRunService
    business_projection: WorkflowBusinessProjectionService | None = None

    def enqueue(
        self,
        workflow_id: str,
        run_id: str,
        inputs: Mapping[str, Any],
        *,
        entity_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        validate_operational_inputs(workflow_id, inputs)
        state = self.coordinator.enqueue(
            workflow_id,
            run_id,
            inputs,
            entity_id=entity_id,
            correlation_id=correlation_id,
        )
        self._project(state)
        return workflow_to_dict(state)

    def advance(self, run_id: str, lifecycle: ClientLifecycleRecord) -> ExecutionOutcome:
        outcome = self.coordinator.advance(run_id, lifecycle)
        self._project(self.runs.load_run(run_id))
        return outcome

    def approve(self, run_id: str, *, approver: str, rationale: str) -> dict[str, Any]:
        state = self.coordinator.approve(run_id, approver=approver, rationale=rationale)
        self._project(state)
        return workflow_to_dict(state)

    def reject_for_revision(self, run_id: str, *, reviewer: str, rationale: str) -> dict[str, Any]:
        current = self.runs.load_run(run_id)
        if current.status is WorkflowStatus.BLOCKED and str(current.blocker or "").startswith("quality_failed:"):
            state = self.runs.request_quality_revision(
                run_id,
                reviewer=reviewer,
                rationale=rationale,
            )
        else:
            state = self.runs.reject_for_revision(run_id, reviewer=reviewer, rationale=rationale)
        self._project(state)
        return workflow_to_dict(state)

    def resume(self, run_id: str) -> dict[str, Any]:
        state = self.runs.load_run(run_id)
        if state.status is not WorkflowStatus.BLOCKED or not state.current_stage_id:
            raise ValueError("workflow run is not blocked at a resumable step")
        stage = state.stage(state.current_stage_id)
        blocker = stage.blocker or state.blocker or ""
        if blocker.startswith("quality_failed:"):
            raise ValueError("quality failure requires an explicit revision request")
        if blocker == "ambiguous_external_action_requires_reconciliation":
            raise ValueError("external action must be reconciled before resume")
        if blocker.startswith("worker_unavailable:"):
            self.coordinator.workers.resolve(
                stage.capability,
                side_effect=stage.side_effect_classification,
            )
        if blocker.startswith("quality_validator_unavailable:") and stage.quality_contract not in self.coordinator.quality_validators:
            raise ValueError("declared quality validator is still unavailable")
        if stage.status is not StageStatus.BLOCKED:
            raise ValueError("workflow step is not resumable")
        state = self.runs.resume_stage(run_id, stage.stage_id, state.input_payload.keys())
        self._project(state)
        return workflow_to_dict(state)

    def status(self, run_id: str) -> dict[str, Any]:
        return workflow_to_dict(self.runs.load_run(run_id))

    def handoff(
        self,
        run_id: str,
        lifecycle: ClientLifecycleRecord,
        additional_inputs: Mapping[str, Any] | None = None,
    ) -> ExecutionOutcome:
        state = self.runs.load_run(run_id)
        definition = self.coordinator.registry.resolve(state.workflow_id)
        if state.status is not WorkflowStatus.COMPLETE:
            raise ValueError("workflow must be complete before handoff")
        if state.approval_required and state.approval_status != "approved":
            raise ValueError("workflow handoff requires explicit approval")
        if not definition.next_workflow_id:
            raise ValueError("workflow has no registered next workflow")
        artifacts = [artifact for stage in state.stages for artifact in stage.output_artifacts]
        if not artifacts:
            raise ValueError("workflow handoff requires a persisted artefact")
        output = self.coordinator.artifacts.root.joinpath(Path(artifacts[-1].location).name)
        try:
            value = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("workflow handoff artefact is unreadable") from exc
        if not isinstance(value, Mapping):
            raise ValueError("workflow handoff artefact must be structured")
        inputs = build_next_workflow_inputs(state, value, additional_inputs)
        next_definition = self.coordinator.registry.resolve(definition.next_workflow_id)
        next_stage = next_definition.stages[0]
        for field in next_stage.output_contract.required_fields:
            if field not in next_stage.input_contract.required_fields:
                inputs.pop(field, None)
        missing = [field for field in next_stage.input_contract.required_fields if field not in inputs or inputs[field] in (None, "", [], {})]
        if missing:
            raise ValueError(f"next workflow requires additional inputs: {','.join(missing)}")
        next_run_id = f"{state.run_id}-{definition.next_workflow_id}"
        self.enqueue(
            definition.next_workflow_id,
            next_run_id,
            inputs,
            entity_id=state.entity_id,
            correlation_id=state.correlation_id,
        )
        self.runs.record_handoff(
            run_id,
            next_workflow_id=definition.next_workflow_id,
            next_run_id=next_run_id,
        )
        self._project(self.runs.load_run(run_id))
        return self.advance(next_run_id, lifecycle)

    def list_run_ids(self) -> list[str]:
        return self.runs.repository.list_run_ids()

    def recover_pending(self) -> int:
        recovered = self.coordinator.recover_pending()
        for run_id in self.list_run_ids():
            self._project(self.runs.load_run(run_id))
        return recovered

    def sync_business_projection(self, run_id: str, *, approver: str, rationale: str) -> dict[str, Any]:
        if self.business_projection is None:
            raise ValueError("business projection is not configured")
        return self.business_projection.sync(
            self.runs.load_run(run_id),
            approver=approver,
            rationale=rationale,
        )

    def _project(self, state: WorkflowState) -> None:
        if self.business_projection is not None:
            self.business_projection.prepare(state)


def build_tony_workflow_runtime(
    root: str | Path,
    *,
    workspace_id: str,
    client_id: str,
    dispatchers: Mapping[str, WorkerAdapter] | None = None,
    environ: Mapping[str, str] | None = None,
    quality_validators: Mapping[str, QualityValidator] | None = None,
) -> TonyWorkflowRuntime:
    """Compose the production workflow runtime without executing any work."""

    scope = hashlib.sha256(f"{workspace_id}:{client_id}".encode("utf-8")).hexdigest()[:24]
    scoped_root = Path(root) / scope
    repository = FileWorkflowRunRepository(
        scoped_root / "runs",
        workspace_id=workspace_id,
        client_id=client_id,
    )
    events = JsonlEventLog(scoped_root / "events", workspace_id=workspace_id)
    runs = WorkflowRunService(
        repository,
        events,
        workspace_id=workspace_id,
        client_id=client_id,
    )
    configured_dispatchers = dict(dispatchers) if dispatchers is not None else build_http_dispatchers(environ)
    validators: dict[str, QualityValidator] = {
        "blueprint_lite_quality_gate": TonyInboundBlueprintLiteService._quality_gate,
        "discovery_preparation_quality_gate": discovery_preparation_quality_gate,
        "growth_sprint_proposal_quality_gate": growth_sprint_proposal_quality_gate,
        "research_evidence_quality_gate": research_evidence_quality_gate,
        "growth_blueprint_quality_gate": growth_blueprint_quality_gate,
    }
    validators.update(dict(quality_validators or {}))
    coordinator = WorkflowExecutionCoordinator(
        registry=build_narratiive_workflow_registry(),
        workers=build_tony_worker_registry(
            configured_dispatchers,
            environ,
            research_adapter=ResearchWorkflowAdapter(scoped_root),
        ),
        runs=runs,
        artifacts=FileWorkflowArtifactStore(scoped_root / "artifacts"),
        quality_validators=validators,
    )
    projection = WorkflowBusinessProjectionService(
        scoped_root / "business-projection",
        dispatcher=configured_dispatchers.get("Notion"),
    )
    return TonyWorkflowRuntime(coordinator=coordinator, runs=runs, business_projection=projection)
