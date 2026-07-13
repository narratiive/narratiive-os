from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .dispatch import DispatchJob
from .dispatch_service import DispatchService
from .models import ArtifactRef


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    outputs: tuple[ArtifactRef, ...]
    next_available_inputs: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.outputs:
            raise ValueError("execution must produce at least one output artifact")


class AgentExecutor(Protocol):
    def execute(self, job: DispatchJob) -> ExecutionResult: ...


class WorkerRunner:
    """Leases one job, executes it, and reports completion or retryable failure."""

    def __init__(
        self,
        *,
        worker_id: str,
        dispatcher: DispatchService,
        executor: AgentExecutor,
        lease_seconds: int = 300,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        self.worker_id = worker_id
        self.dispatcher = dispatcher
        self.executor = executor
        self.lease_seconds = lease_seconds

    def run_once(self) -> DispatchJob | None:
        job = self.dispatcher.lease_next(self.worker_id, self.lease_seconds)
        if job is None:
            return None
        try:
            result = self.executor.execute(job)
            self.dispatcher.complete_job(
                job.job_id,
                self.worker_id,
                result.outputs,
                result.next_available_inputs,
                result.metadata,
            )
        except Exception as exc:
            self.dispatcher.fail_job(
                job.job_id,
                self.worker_id,
                f"{type(exc).__name__}: {exc}",
                retryable=True,
            )
        return job


class JsonArtifactExecutor:
    """Reference executor that writes deterministic JSON artifacts locally.

    It proves the worker contract without calling an AI model. Real provider
    adapters should implement AgentExecutor and return the same ExecutionResult.
    """

    def __init__(self, root: str | Path, output_type_by_stage: dict[str, str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_type_by_stage = dict(output_type_by_stage)

    def execute(self, job: DispatchJob) -> ExecutionResult:
        output_type = self.output_type_by_stage.get(job.stage_id)
        if not output_type:
            raise ValueError(f"no output type configured for stage: {job.stage_id}")
        run_dir = self.root / job.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / f"{job.stage_id}.json"
        payload = {
            "job_id": job.job_id,
            "run_id": job.run_id,
            "stage_id": job.stage_id,
            "agent_ref": job.agent_ref,
            "input": job.payload,
            "executor": "json_artifact_reference",
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifact = ArtifactRef(
            artifact_id=f"{job.run_id}--{job.stage_id}--output",
            artifact_type=output_type,
            location=str(target),
            metadata={"executor": "json_artifact_reference"},
        )
        return ExecutionResult(
            outputs=(artifact,),
            next_available_inputs=(output_type,),
            metadata={"executor": "json_artifact_reference", "output_path": str(target)},
        )
