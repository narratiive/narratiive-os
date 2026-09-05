from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import StageRecord, WorkflowState


def _validate_contract_fields(fields: tuple[str, ...], label: str) -> None:
    if any(not field.strip() for field in fields):
        raise ValueError(f"{label} fields must not be blank")
    if len(fields) != len(set(fields)):
        raise ValueError(f"{label} fields must be unique")


@dataclass(frozen=True, slots=True)
class InputContract:
    required_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_contract_fields(self.required_fields, "input contract")


@dataclass(frozen=True, slots=True)
class OutputContract:
    required_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_contract_fields(self.required_fields, "output contract")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    required: bool = False
    before_external_action: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.required, bool) or not isinstance(self.before_external_action, bool):
            raise ValueError("approval policy fields must be booleans")


@dataclass(frozen=True, slots=True)
class StageDefinition:
    stage_id: str
    agent_ref: str
    required_inputs: tuple[str, ...] = ()
    capability: str = ""
    input_contract: InputContract = InputContract()
    output_contract: OutputContract = OutputContract()
    quality_contract: str = ""
    retry_policy: RetryPolicy = RetryPolicy()
    approval_policy: ApprovalPolicy = ApprovalPolicy()
    side_effect_classification: str = "preparation"

    def __post_init__(self) -> None:
        if not self.stage_id.strip() or not (self.agent_ref.strip() or self.capability.strip()):
            raise ValueError("stage_id and agent_ref or capability must not be empty")
        if self.side_effect_classification not in {"none", "preparation", "external_read", "external_write"}:
            raise ValueError(f"invalid side_effect_classification: {self.side_effect_classification}")


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    workflow_id: str
    stages: tuple[StageDefinition, ...]
    schema_version: int = 1
    approval_required: bool = False
    entity_type: str = "client"
    next_workflow_id: str = ""
    failure_policy: str = "block_and_escalate"

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.stages:
            raise ValueError("workflow_id and at least one stage are required")
        stage_ids = [stage.stage_id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("stage_id values must be unique")
        if not self.entity_type.strip() or not self.failure_policy.strip():
            raise ValueError("entity_type and failure_policy must not be empty")

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
                    agent_ref=stage.agent_ref or f"capability:{stage.capability}",
                    required_inputs=stage.required_inputs,
                    capability=stage.capability,
                    expected_outputs=stage.output_contract.required_fields,
                    quality_contract=stage.quality_contract,
                    max_attempts=stage.retry_policy.max_attempts,
                    step_approval_required=stage.approval_policy.required,
                    side_effect_classification=stage.side_effect_classification,
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
        capability = str(raw.get("capability", "")).strip()
        if not stage_id or not (agent_ref or capability):
            raise ValueError("stage_id and agent_ref or capability must not be empty")
        if stage_id in seen:
            raise ValueError(f"duplicate stage_id: {stage_id}")
        seen.add(stage_id)
        required = tuple(str(item).strip() for item in raw.get("required_inputs", []) if str(item).strip())
        input_contract = _contract_fields(raw.get("input_contract"), "input_contract")
        output_contract = _contract_fields(raw.get("output_contract"), "output_contract")
        retry_raw = raw.get("retry_policy") or {}
        approval_raw = raw.get("approval_policy") or {}
        if not isinstance(retry_raw, dict) or not isinstance(approval_raw, dict):
            raise ValueError("retry_policy and approval_policy must be objects")
        side_effect = str(raw.get("side_effect_classification", "preparation")).strip()
        if side_effect not in {"none", "preparation", "external_read", "external_write"}:
            raise ValueError(f"invalid side_effect_classification: {side_effect}")
        required_value = approval_raw.get("required", False)
        before_external = approval_raw.get("before_external_action", True)
        if not isinstance(required_value, bool) or not isinstance(before_external, bool):
            raise ValueError("approval_policy fields must be booleans")
        stages.append(
            StageDefinition(
                stage_id=stage_id,
                agent_ref=agent_ref,
                required_inputs=required,
                capability=capability,
                input_contract=InputContract(input_contract),
                output_contract=OutputContract(output_contract),
                quality_contract=str(raw.get("quality_contract", "")).strip(),
                retry_policy=RetryPolicy(int(retry_raw.get("max_attempts", 1))),
                approval_policy=ApprovalPolicy(
                    required=required_value,
                    before_external_action=before_external,
                ),
                side_effect_classification=side_effect,
            )
        )

    approval_required = data.get("approval_required", False)
    if not isinstance(approval_required, bool):
        raise ValueError("approval_required must be a boolean")
    return WorkflowDefinition(
        workflow_id=workflow_id,
        stages=tuple(stages),
        schema_version=version,
        approval_required=approval_required,
        entity_type=str(data.get("entity_type", "client")).strip() or "client",
        next_workflow_id=str(data.get("next_workflow_id", "")).strip(),
        failure_policy=str(data.get("failure_policy", "block_and_escalate")).strip() or "block_and_escalate",
    )


def _contract_fields(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    fields = value.get("required_fields") or []
    if not isinstance(fields, list):
        raise ValueError(f"{label}.required_fields must be a list")
    return tuple(str(item).strip() for item in fields if str(item).strip())
