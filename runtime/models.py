from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    RETRY_REQUIRED = "retry_required"
    REVISION_REQUIRED = "revision_required"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    location: str
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id must not be empty")
        if not self.artifact_type.strip():
            raise ValueError("artifact_type must not be empty")
        if not self.location.strip():
            raise ValueError("location must not be empty")


@dataclass(slots=True)
class StageRecord:
    stage_id: str
    agent_ref: str
    status: StageStatus = StageStatus.NOT_STARTED
    required_inputs: tuple[str, ...] = ()
    input_artifacts: list[ArtifactRef] = field(default_factory=list)
    output_artifacts: list[ArtifactRef] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    retry_count: int = 0
    revision_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None

    def mark_started(self) -> None:
        self.started_at = _utc_now()

    def mark_completed(self) -> None:
        self.completed_at = _utc_now()


@dataclass(slots=True)
class WorkflowState:
    workflow_id: str
    run_id: str
    stages: list[StageRecord]
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    current_stage_id: str | None = None
    revision_owner: str | None = None
    approval_required: bool = False
    workspace_id: str = "legacy"
    client_id: str = "legacy"
    created_at: str = field(default_factory=lambda: _utc_now())
    updated_at: str = field(default_factory=lambda: _utc_now())

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise ValueError("workflow_id must not be empty")
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.workspace_id.strip() or not self.client_id.strip():
            raise ValueError("workspace_id and client_id must not be empty")
        stage_ids = [stage.stage_id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("stage_id values must be unique")

    def stage(self, stage_id: str) -> StageRecord:
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        raise KeyError(f"unknown stage: {stage_id}")

    def touch(self) -> None:
        self.updated_at = _utc_now()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
