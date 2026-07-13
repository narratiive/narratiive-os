from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from .dispatch import DispatchJob, DispatchQueue, JobStatus
from .models import ArtifactRef, StageStatus
from .repositories import EventLog, WorkflowEvent, WorkflowRunRepository
from .run_service import WorkflowRunService


class DispatchService:
    """Coordinates persisted workflow stages with an external worker queue."""

    def __init__(
        self,
        runs: WorkflowRunRepository,
        event_log: EventLog,
        queue: DispatchQueue,
        run_service: WorkflowRunService,
    ) -> None:
        self.runs = runs
        self.event_log = event_log
        self.queue = queue
        self.run_service = run_service

    def enqueue_current_stage(self, run_id: str) -> DispatchJob:
        state = self.runs.load(run_id)
        if not state.current_stage_id:
            raise ValueError("workflow has no current stage")
        stage = state.stage(state.current_stage_id)
        if stage.status != StageStatus.READY:
            raise ValueError(f"stage is not ready for dispatch: {stage.status.value}")

        job = DispatchJob(
            job_id=f"{run_id}--{stage.stage_id}",
            run_id=run_id,
            stage_id=stage.stage_id,
            agent_ref=stage.agent_ref,
            payload={
                "workflow_id": state.workflow_id,
                "run_id": run_id,
                "stage_id": stage.stage_id,
                "agent_ref": stage.agent_ref,
                "input_artifacts": [
                    {
                        "artifact_id": item.artifact_id,
                        "artifact_type": item.artifact_type,
                        "location": item.location,
                        "checksum": item.checksum,
                        "metadata": item.metadata,
                    }
                    for item in stage.input_artifacts
                ],
                "missing_inputs": list(stage.missing_inputs),
            },
        )
        queued = self.queue.enqueue(job)
        self._event(
            run_id,
            "dispatch.enqueued",
            {"job_id": queued.job_id, "stage_id": stage.stage_id, "agent_ref": stage.agent_ref},
        )
        return queued

    def lease_next(self, worker_id: str, lease_seconds: int = 300) -> DispatchJob | None:
        job = self.queue.lease_next(worker_id, lease_seconds)
        if job is None:
            return None
        state = self.runs.load(job.run_id)
        stage = state.stage(job.stage_id)
        if stage.status == StageStatus.READY:
            self.run_service.start_stage(job.run_id, job.stage_id)
        self._event(
            job.run_id,
            "dispatch.leased",
            {
                "job_id": job.job_id,
                "stage_id": job.stage_id,
                "worker_id": worker_id,
                "attempt": job.attempt,
                "lease_expires_at": job.lease_expires_at,
            },
        )
        return job

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        outputs: Iterable[ArtifactRef],
        next_available_inputs: Iterable[str] = (),
        result: dict[str, object] | None = None,
    ):
        job = self.queue.get(job_id)
        if job.status == JobStatus.COMPLETED:
            return self.runs.load(job.run_id)
        output_list = list(outputs)
        state = self.run_service.complete_stage(
            job.run_id,
            job.stage_id,
            output_list,
            next_available_inputs,
        )
        self.queue.complete(
            job_id,
            worker_id,
            result
            or {
                "output_artifact_ids": [item.artifact_id for item in output_list],
                "workflow_status": state.status.value,
                "next_stage_id": state.current_stage_id,
            },
        )
        self._event(
            job.run_id,
            "dispatch.completed",
            {
                "job_id": job_id,
                "stage_id": job.stage_id,
                "worker_id": worker_id,
                "output_artifact_ids": [item.artifact_id for item in output_list],
            },
        )
        return state

    def fail_job(
        self,
        job_id: str,
        worker_id: str,
        error: str,
        retryable: bool = True,
    ):
        job = self.queue.get(job_id)
        updated = self.queue.fail(job_id, worker_id, error, retryable)
        if retryable:
            state = self.run_service.request_retry(job.run_id, job.stage_id, error)
        else:
            state = self.runs.load(job.run_id)
        self._event(
            job.run_id,
            "dispatch.failed",
            {
                "job_id": job_id,
                "stage_id": job.stage_id,
                "worker_id": worker_id,
                "retryable": retryable,
                "job_status": updated.status.value,
                "error": error,
            },
        )
        return state

    def _event(self, run_id: str, event_type: str, payload: dict[str, object]) -> None:
        self.event_log.append(
            WorkflowEvent.create(
                event_id=f"evt-{uuid4().hex}",
                run_id=run_id,
                event_type=event_type,
                payload=payload,
            )
        )
