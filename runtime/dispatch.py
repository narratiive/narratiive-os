from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class JobStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"


class JobNotFound(KeyError):
    pass


class LeaseConflict(RuntimeError):
    pass


@dataclass(slots=True)
class DispatchJob:
    job_id: str
    run_id: str
    stage_id: str
    agent_ref: str
    payload: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    attempt: int = 0
    leased_by: str | None = None
    lease_expires_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: _utc_now())
    updated_at: str = field(default_factory=lambda: _utc_now())

    def __post_init__(self) -> None:
        for field_name in ("job_id", "run_id", "stage_id", "agent_ref"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")

    def lease_is_active(self, now: datetime | None = None) -> bool:
        if self.status != JobStatus.LEASED or not self.lease_expires_at:
            return False
        current = now or datetime.now(timezone.utc)
        return datetime.fromisoformat(self.lease_expires_at) > current


class DispatchQueue(Protocol):
    def enqueue(self, job: DispatchJob) -> DispatchJob: ...
    def get(self, job_id: str) -> DispatchJob: ...
    def lease_next(self, worker_id: str, lease_seconds: int = 300) -> DispatchJob | None: ...
    def complete(self, job_id: str, worker_id: str, result: dict[str, Any]) -> DispatchJob: ...
    def fail(self, job_id: str, worker_id: str, error: str, retryable: bool) -> DispatchJob: ...


class FileDispatchQueue:
    """Small durable queue with atomic snapshots and worker leases."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def enqueue(self, job: DispatchJob) -> DispatchJob:
        if self._path(job.job_id).exists():
            existing = self.get(job.job_id)
            if existing.run_id == job.run_id and existing.stage_id == job.stage_id:
                return existing
            raise ValueError(f"job already exists with different identity: {job.job_id}")
        self._write(job)
        return job

    def get(self, job_id: str) -> DispatchJob:
        path = self._path(job_id)
        if not path.exists():
            raise JobNotFound(job_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["status"] = JobStatus(payload["status"])
        return DispatchJob(**payload)

    def lease_next(self, worker_id: str, lease_seconds: int = 300) -> DispatchJob | None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(timezone.utc)
        candidates = sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime)
        for path in candidates:
            job = self.get(path.stem)
            if job.status == JobStatus.PENDING or (
                job.status == JobStatus.LEASED and not job.lease_is_active(now)
            ):
                job.status = JobStatus.LEASED
                job.leased_by = worker_id
                job.lease_expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()
                job.attempt += 1
                job.updated_at = _utc_now()
                self._write(job)
                return job
        return None

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any]) -> DispatchJob:
        job = self.get(job_id)
        if job.status == JobStatus.COMPLETED:
            return job
        self._require_lease(job, worker_id)
        job.status = JobStatus.COMPLETED
        job.result = result
        job.error = None
        job.lease_expires_at = None
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def fail(self, job_id: str, worker_id: str, error: str, retryable: bool) -> DispatchJob:
        job = self.get(job_id)
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            return job
        self._require_lease(job, worker_id)
        job.error = error.strip() or "worker failure"
        job.leased_by = None
        job.lease_expires_at = None
        job.status = JobStatus.PENDING if retryable else JobStatus.FAILED
        job.updated_at = _utc_now()
        self._write(job)
        return job

    def _require_lease(self, job: DispatchJob, worker_id: str) -> None:
        if job.status != JobStatus.LEASED or job.leased_by != worker_id:
            raise LeaseConflict(f"job {job.job_id} is not leased by {worker_id}")
        if not job.lease_is_active():
            raise LeaseConflict(f"lease expired for job {job.job_id}")

    def _path(self, job_id: str) -> Path:
        safe = job_id.strip()
        if not safe or safe in {".", ".."} or "/" in safe or "\\" in safe:
            raise ValueError("unsafe job_id")
        return self.root / f"{safe}.json"

    def _write(self, job: DispatchJob) -> None:
        path = self._path(job.job_id)
        temp = path.with_suffix(".tmp")
        payload = asdict(job)
        payload["status"] = job.status.value
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
