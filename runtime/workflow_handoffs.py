from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from runtime.models import WorkflowState


def build_next_workflow_inputs(
    source: WorkflowState,
    output: Mapping[str, Any],
    additional_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build explicit cross-workflow inputs without inventing missing evidence."""
    combined = {**source.input_payload, **dict(output), **dict(additional_inputs or {})}
    if source.workflow_id == "growth_diagnostic_to_blueprint_lite":
        combined.setdefault("diagnostic_evidence", source.input_payload.get("diagnostic_input_package"))
        if not isinstance(combined.get("company_context"), Mapping):
            name = str(combined.get("company") or combined.get("company_name") or "").strip()
            combined["company_context"] = {"name": name, "source_ref": f"workflow_run:{source.run_id}"}
    elif source.workflow_id == "blueprint_lite_to_discovery_preparation":
        combined.setdefault("commercial_context", combined.get("company_context"))
    combined["_lineage"] = {
        "parent_workflow_id": source.workflow_id,
        "parent_run_id": source.run_id,
        "parent_artifact_ids": [
            artifact.artifact_id
            for stage in source.stages
            for artifact in stage.output_artifacts
        ],
    }
    return combined
