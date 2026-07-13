from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import StageRecord, WorkflowState


@dataclass(frozen=True, slots=True)
class StageDefinition:
    stage_id: str
    agent_ref: str
    required_inputs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    workflow_id: str
    stages: tuple[StageDefinition, ...]
    schema_version: int = 1
    approval_required: bool = False

    def new_state(
        self,
        run_id: str,
        *,
        workspace_id: str = "legacy",
        client_id: str = "legacy",
    ) -> WorkflowState:
        return WorkflowState(
            workflow_id=self.workflow_id,
            run_id=run_id,
            stages=[
                StageRecord(
                    stage_id=stage.stage_id,
                    agent_ref=stage.agent_ref,
                    required_inputs=stage.required_inputs,
                )
                for stage in self.stages
            ],
            approval_required=self.approval_required,
            workspace_id=workspace_id,
            client_id=client_id,
        )


def load_workflow_definition(path: str | Path) -> WorkflowDefinition:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return workflow_definition_from_dict(data)


def workflow_definition_from_dict(data: dict[str, Any]) -> WorkflowDefinition:
    version = int(data.get("schema_version", 1))
    if version != 1:
        raise ValueError(f"unsupported workflow definition schema_version: {version}")
    workflow_id = str(data.get("workflow_id", "")).strip()
    if not workflow_id:
        raise ValueError("workflow_id must not be empty")
    raw_stages = data.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ValueError("workflow must define at least one stage")

    stages: list[StageDefinition] = []
    seen: set[str] = set()
    for raw in raw_stages:
        if not isinstance(raw, dict):
            raise ValueError("each stage definition must be an object")
        stage_id = str(raw.get("stage_id", "")).strip()
        agent_ref = str(raw.get("agent_ref", "")).strip()
        if not stage_id or not agent_ref:
            raise ValueError("stage_id and agent_ref must not be empty")
        if stage_id in seen:
            raise ValueError(f"duplicate stage_id: {stage_id}")
        seen.add(stage_id)
        required = tuple(str(item).strip() for item in raw.get("required_inputs", []) if str(item).strip())
        stages.append(StageDefinition(stage_id, agent_ref, required))

    approval_required = data.get("approval_required", False)
    if not isinstance(approval_required, bool):
        raise ValueError("approval_required must be a boolean")
    return WorkflowDefinition(
        workflow_id=workflow_id,
        stages=tuple(stages),
        schema_version=version,
        approval_required=approval_required,
    )
