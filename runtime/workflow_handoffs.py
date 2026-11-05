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
    elif source.workflow_id == "discovery_evidence_to_growth_sprint_proposal":
        combined.setdefault("approved_growth_sprint_scope", output.get("proposed_scope"))
        combined.setdefault("research_requirements", {"workstreams_and_questions": output.get("workstreams_and_questions", [])})
        combined.setdefault("client_context", combined.get("commercial_context"))
    elif source.workflow_id == 'growth_blueprint_deliverable_production':
        blueprint = source.input_payload.get('quality_accepted_growth_blueprint')
        if isinstance(blueprint, Mapping):
            combined['growth_blueprint'] = dict(blueprint)
    elif source.workflow_id == "strategic_synthesis_to_strategy_thesis":
        artifact = next(
            (stage.output_artifacts[-1] for stage in reversed(source.stages) if stage.output_artifacts),
            None,
        )
        thesis = output.get("strategy_thesis")
        if artifact is not None and artifact.checksum and isinstance(thesis, Mapping):
            combined["approved_strategy_thesis"] = dict(thesis)
            combined["strategy_thesis_identity"] = {
                "artifact_id": artifact.artifact_id,
                "version": int(artifact.metadata.get("version") or 1),
                "checksum": artifact.checksum,
            }
    source_lineage = source.input_payload.get("_lineage")
    inherited_manual_recovery = (
        source_lineage.get("manual_recovery")
        if isinstance(source_lineage, Mapping) and isinstance(source_lineage.get("manual_recovery"), Mapping)
        else None
    )
    direct_manual_recovery = next(
        (
            item
            for item in reversed(source.approval_history)
            if item.get("decision") == "manual_recovery_approved"
        ),
        None,
    )
    recovery = direct_manual_recovery or inherited_manual_recovery
    manual_recovery = (
        {
            "recovery_id": recovery.get("recovery_id"),
            "artifact_id": recovery.get("artifact_id"),
            "artifact_checksum": recovery.get("artifact_checksum"),
            "artifact_title": recovery.get("artifact_title"),
            "artifact_version": recovery.get("artifact_version"),
            "source_uri": recovery.get("source_uri"),
            "prior_blocker": recovery.get("prior_blocker"),
            "automated_completion": False,
        }
        if recovery
        else None
    )
    combined["_lineage"] = {
        "parent_workflow_id": source.workflow_id,
        "parent_run_id": source.run_id,
        "parent_artifact_ids": [
            artifact.artifact_id
            for stage in source.stages
            for artifact in stage.output_artifacts
        ],
        "manual_recovery": manual_recovery,
    }
    return combined
