from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.client_lifecycle import ClientLifecycleRecord
from runtime.models import StageStatus, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
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
from runtime.workflow_registry import build_narratiive_workflow_registry


@dataclass(slots=True)
class TonyWorkflowRuntime:
    """Queryable application surface for one workspace/client execution scope."""

    coordinator: WorkflowExecutionCoordinator
    runs: WorkflowRunService

    def enqueue(
        self,
        workflow_id: str,
        run_id: str,
        inputs: Mapping[str, Any],
        *,
        entity_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        state = self.coordinator.enqueue(
            workflow_id,
            run_id,
            inputs,
            entity_id=entity_id,
            correlation_id=correlation_id,
        )
        return workflow_to_dict(state)

    def advance(self, run_id: str, lifecycle: ClientLifecycleRecord) -> ExecutionOutcome:
        return self.coordinator.advance(run_id, lifecycle)

    def approve(self, run_id: str, *, approver: str, rationale: str) -> dict[str, Any]:
        return workflow_to_dict(
            self.coordinator.approve(run_id, approver=approver, rationale=rationale)
        )

    def reject_for_revision(self, run_id: str, *, reviewer: str, rationale: str) -> dict[str, Any]:
        return workflow_to_dict(
            self.runs.reject_for_revision(run_id, reviewer=reviewer, rationale=rationale)
        )

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
        return workflow_to_dict(
            self.runs.resume_stage(run_id, stage.stage_id, state.input_payload.keys())
        )

    def status(self, run_id: str) -> dict[str, Any]:
        return workflow_to_dict(self.runs.load_run(run_id))

    def list_run_ids(self) -> list[str]:
        return self.runs.repository.list_run_ids()

    def recover_pending(self) -> int:
        return self.coordinator.recover_pending()


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
    }
    validators.update(dict(quality_validators or {}))
    coordinator = WorkflowExecutionCoordinator(
        registry=build_narratiive_workflow_registry(),
        workers=build_tony_worker_registry(configured_dispatchers, environ),
        runs=runs,
        artifacts=FileWorkflowArtifactStore(scoped_root / "artifacts"),
        quality_validators=validators,
    )
    return TonyWorkflowRuntime(coordinator=coordinator, runs=runs)
