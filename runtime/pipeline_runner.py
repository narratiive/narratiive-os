from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .definitions import WorkflowDefinition
from .dispatch import DispatchQueue
from .dispatch_service import DispatchService
from .execution_package import ExecutionPackage
from .models import StageStatus, WorkflowState, WorkflowStatus
from .provider import ProviderResponse
from .repositories import EventLog, WorkflowRunRepository
from .run_service import WorkflowRunService
from .worker import AgentExecutor, WorkerRunner


@dataclass(slots=True)
class DeterministicProvider:
    """Fixture-backed provider used for repeatable end-to-end pipeline runs."""

    outputs: Mapping[str, str]
    metadata: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list, init=False)

    def generate(self, package: ExecutionPackage) -> ProviderResponse:
        try:
            content = self.outputs[package.stage_id]
        except KeyError as exc:
            raise ValueError(
                f"deterministic output missing for stage: {package.stage_id}"
            ) from exc
        self.calls.append(package.stage_id)
        return ProviderResponse(
            job_id=package.job_id,
            run_id=package.run_id,
            stage_id=package.stage_id,
            output_type=package.expected_output_type,
            content=content,
            metadata={
                "provider": "deterministic-fixture",
                "input_artifact_ids": [
                    item["artifact_id"] for item in package.input_artifacts
                ],
                "memory_ids": [
                    item["memory_id"] for item in package.memory_records
                ],
                "scorecard_recommendation": (
                    package.confidence_scorecard["recommendation"]
                    if package.confidence_scorecard is not None
                    else None
                ),
                **dict(self.metadata.get(package.stage_id, {})),
            },
        )

    @classmethod
    def from_fixture(cls, fixture: Mapping[str, Any]) -> "DeterministicProvider":
        raw_outputs = fixture.get("stage_outputs")
        if not isinstance(raw_outputs, dict) or not raw_outputs:
            raise ValueError("fixture must define stage_outputs")
        outputs = {str(key): str(value) for key, value in raw_outputs.items()}
        raw_metadata = fixture.get("stage_metadata") or {}
        if not isinstance(raw_metadata, dict):
            raise ValueError("stage_metadata must be an object")
        metadata = {
            str(stage_id): dict(value)
            for stage_id, value in raw_metadata.items()
            if isinstance(value, dict)
        }
        return cls(outputs=outputs, metadata=metadata)


class PipelineRunner:
    """Executes a persisted workflow in definition order until complete or retryable failure."""

    def __init__(
        self,
        *,
        definition: WorkflowDefinition,
        runs: WorkflowRunRepository,
        event_log: EventLog,
        queue: DispatchQueue,
        executor: AgentExecutor,
        worker_id: str = "pipeline-runner",
    ) -> None:
        self.definition = definition
        self.runs = runs
        self.run_service = WorkflowRunService(runs, event_log)
        self.dispatch = DispatchService(runs, event_log, queue, self.run_service)
        self.worker = WorkerRunner(
            worker_id=worker_id,
            dispatcher=self.dispatch,
            executor=executor,
        )

    def run(
        self,
        run_id: str,
        available_inputs: Iterable[str],
        *,
        client_id: str | None = None,
        scoring_input: Mapping[str, Any] | None = None,
    ) -> WorkflowState:
        supplied_inputs = set(available_inputs)
        if not self.runs.exists(run_id):
            self.run_service.create_run(self.definition, run_id, supplied_inputs)

        while True:
            state = self.runs.load(run_id)
            if state.workflow_id != self.definition.workflow_id:
                raise ValueError(
                    f"run {run_id} belongs to workflow {state.workflow_id}, "
                    f"not {self.definition.workflow_id}"
                )
            if state.status == WorkflowStatus.COMPLETE:
                return state
            if not state.current_stage_id:
                return state

            stage = state.stage(state.current_stage_id)
            if stage.status in {
                StageStatus.BLOCKED,
                StageStatus.RETRY_REQUIRED,
            }:
                available = supplied_inputs | {
                    artifact.artifact_type for artifact in stage.input_artifacts
                }
                state = self.run_service.resume_stage(
                    run_id,
                    stage.stage_id,
                    available,
                )
                stage = state.stage(stage.stage_id)
                if stage.status != StageStatus.READY:
                    return state

            if stage.status != StageStatus.READY:
                return state

            context = {"client_id": client_id} if client_id is not None else None
            if stage.stage_id == "quality_reviewer" and scoring_input is not None:
                context = {
                    **dict(context or {}),
                    "scoring_input": dict(scoring_input),
                }
            self.dispatch.enqueue_current_stage(run_id, context=context)
            job = self.worker.run_once()
            if job is None:
                return self.runs.load(run_id)

            state = self.runs.load(run_id)
            if state.stage(job.stage_id).status == StageStatus.RETRY_REQUIRED:
                return state


def load_pipeline_fixture(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("pipeline fixture must be a JSON object")
    return data
