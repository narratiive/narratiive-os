from __future__ import annotations

from typing import Any

from .models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus


def artifact_to_dict(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "location": artifact.location,
        "checksum": artifact.checksum,
        "metadata": artifact.metadata,
    }


def artifact_from_dict(data: dict[str, Any]) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=data["artifact_id"],
        artifact_type=data["artifact_type"],
        location=data["location"],
        checksum=data.get("checksum"),
        metadata=dict(data.get("metadata") or {}),
    )


def stage_to_dict(stage: StageRecord) -> dict[str, Any]:
    return {
        "stage_id": stage.stage_id,
        "agent_ref": stage.agent_ref,
        "status": stage.status.value,
        "required_inputs": list(stage.required_inputs),
        "input_artifacts": [artifact_to_dict(item) for item in stage.input_artifacts],
        "output_artifacts": [artifact_to_dict(item) for item in stage.output_artifacts],
        "missing_inputs": list(stage.missing_inputs),
        "failure_reason": stage.failure_reason,
        "retry_count": stage.retry_count,
        "revision_count": stage.revision_count,
        "started_at": stage.started_at,
        "completed_at": stage.completed_at,
    }


def stage_from_dict(data: dict[str, Any]) -> StageRecord:
    return StageRecord(
        stage_id=data["stage_id"],
        agent_ref=data["agent_ref"],
        status=StageStatus(data.get("status", StageStatus.NOT_STARTED.value)),
        required_inputs=tuple(data.get("required_inputs") or ()),
        input_artifacts=[artifact_from_dict(item) for item in data.get("input_artifacts") or []],
        output_artifacts=[artifact_from_dict(item) for item in data.get("output_artifacts") or []],
        missing_inputs=list(data.get("missing_inputs") or []),
        failure_reason=data.get("failure_reason"),
        retry_count=int(data.get("retry_count", 0)),
        revision_count=int(data.get("revision_count", 0)),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
    )


def workflow_to_dict(state: WorkflowState) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow_id": state.workflow_id,
        "run_id": state.run_id,
        "status": state.status.value,
        "current_stage_id": state.current_stage_id,
        "revision_owner": state.revision_owner,
        "approval_required": state.approval_required,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "stages": [stage_to_dict(stage) for stage in state.stages],
    }


def workflow_from_dict(data: dict[str, Any]) -> WorkflowState:
    schema_version = int(data.get("schema_version", 1))
    if schema_version != 1:
        raise ValueError(f"unsupported workflow schema_version: {schema_version}")
    return WorkflowState(
        workflow_id=data["workflow_id"],
        run_id=data["run_id"],
        stages=[stage_from_dict(stage) for stage in data.get("stages") or []],
        status=WorkflowStatus(data.get("status", WorkflowStatus.ACTIVE.value)),
        current_stage_id=data.get("current_stage_id"),
        revision_owner=data.get("revision_owner"),
        approval_required=bool(data.get("approval_required", False)),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
