#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleRecord, ClientLifecycleStage
from runtime.research_engine import slugify
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_tony_workflow_runtime import _blueprint_output
from tests.test_workflow_quality import (
    blueprint_director_output,
    discovery_output,
    growth_blueprint_output,
    proposal_output,
    strategic_synthesis_output,
    strategy_thesis_output,
)


CLIENT_ID = "safe-golden-path-certification"
COMPANY = "Northstar Works — SYNTHETIC ENGINEERING FIXTURE"


class _Fallback:
    def execute(self, command, objects):
        return CommandResponse("fallback", "healthy", "fallback", {})


def _lifecycle() -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=CLIENT_ID,
        client_name=COMPANY,
        stage=ClientLifecycleStage.BLUEPRINT_LITE,
        owner="Tony",
        next_action="Prepare the next governed internal artefact.",
        evidence=("synthetic:golden-path-certification",),
        acquisition_path=AcquisitionPath.INBOUND,
    )


def _approval(service, run_id: str, token: str, label: str) -> None:
    instruction = f"TEST APPROVAL — I explicitly approve the current {label} artefact for run {run_id} for internal continuation only."
    response = service.execute(
        f"/approve {run_id} because {instruction}",
        [],
        principal_id="matt:synthetic-certification",
        inputs={
            "approval_token": token,
            "approval_decision_evidence": {
                "explicit_decision_intent": "approve",
                "human_instruction": instruction,
                "human_instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
                "turn_run_id": f"certification:{run_id}:{label}",
                "verbatim_current_human_instruction_verified": True,
            },
        },
    )
    if response.status == "error":
        raise RuntimeError(response.message)


def _states(backend: FileWorkflowCommandBackend) -> dict[str, object]:
    return {state.workflow_id: state for state in backend.list_states()}


def run(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    blueprint_attempts = 0

    def claude(contract):
        nonlocal blueprint_attempts
        context = contract.get("target", {}).get("workflow_context", {})
        target = contract.get("target", {})
        workflow_id = context.get("workflow_id")
        if workflow_id == "blueprint_lite_to_discovery_preparation":
            return discovery_output()
        if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
            return proposal_output()
        if workflow_id == "research_to_strategic_synthesis":
            return strategic_synthesis_output()
        if workflow_id == "strategic_synthesis_to_strategy_thesis":
            return strategy_thesis_output()
        if workflow_id == "strategy_thesis_to_growth_blueprint":
            if context.get("stage_id") == "direct_growth_blueprint":
                client = target.get("client_context", {})
                return blueprint_director_output(
                    client_name=str(client.get("name") or client.get("company") or COMPANY)
                )
            blueprint_attempts += 1
            candidate = growth_blueprint_output()
            if blueprint_attempts == 1:
                candidate["central_thesis"] = {
                    "insight": "Generic marketing opportunity",
                    "why_non_obvious": "Not demonstrated",
                    "competitor_substitution_test": "Any competitor could use this",
                    "commercial_consequence": "Do more marketing activity",
                    "evidence_refs": [],
                }
            return candidate
        return _blueprint_output()

    dispatchers = {"Claude": claude}
    runtime = build_tony_workflow_runtime(
        root,
        workspace_id="golden-path-certification",
        client_id=CLIENT_ID,
        dispatchers=dispatchers,
        environ={},
    )
    research = (
        runtime.coordinator.artifacts.root.parent
        / "research"
        / "workspaces"
        / slugify("golden-path-certification")
    )
    research.mkdir(parents=True)
    (research / "category.md").write_text(
        "SYNTHETIC category evidence says broad category language makes the offer difficult to distinguish, prevents confident buyer choice and leaves the central strategic decision unresolved.",
        encoding="utf-8",
    )
    (research / "audience.md").write_text(
        "SYNTHETIC audience evidence records that urgent buyers seek specific proof, clearer commercial outcomes and confidence before they enter a serious conversation.",
        encoding="utf-8",
    )
    initial_inputs = {
        "diagnostic_input_package": {
            "overall_score": 41,
            "main_blockage": "The synthetic offer is difficult to distinguish.",
            "raw_answers": {"challenge": "SYNTHETIC evidence only"},
        },
        "company": COMPANY,
        "email": "northstar-works@acceptance.invalid",
    }
    runtime.enqueue(
        "growth_diagnostic_to_blueprint_lite",
        "safe-golden-path-run",
        initial_inputs,
        entity_id=CLIENT_ID,
        correlation_id="safe-golden-path-correlation",
    )
    runtime.enqueue(
        "growth_diagnostic_to_blueprint_lite",
        "safe-golden-path-run",
        initial_inputs,
        entity_id=CLIENT_ID,
        correlation_id="safe-golden-path-correlation",
    )
    runtime.advance("safe-golden-path-run", _lifecycle())

    backend = FileWorkflowCommandBackend(root, dispatchers=dispatchers, environ={})
    service = TonyWorkflowCommandService(_Fallback(), backend)
    initial = service.execute("/workflow safe-golden-path-run", [])
    _approval(service, "safe-golden-path-run", initial.data["approval_token"], "Blueprint Lite")
    discovery = service.execute("/continue safe-golden-path-run", [])
    _approval(service, discovery.data["run_id"], discovery.data["approval_token"], "Discovery Preparation")
    proposal = service.execute(
        f"/continue {discovery.data['run_id']}",
        [],
        inputs={
            "discovery_evidence": {
                "notes": "SYNTHETIC sourced Discovery evidence confirms that differentiation and proof timing remain unresolved.",
                "sources": [{
                    "source_id": "safe-discovery-notes",
                    "source_type": "notes",
                    "location": "meeting:synthetic-golden-path",
                }],
            }
        },
    )
    _approval(service, proposal.data["run_id"], proposal.data["approval_token"], "Growth Sprint proposal")
    thesis = service.execute(
        f"/continue {proposal.data['run_id']}",
        [],
        inputs={
            "research_sources": [
                {"source_id": "safe-category", "source_type": "document", "uri": "category.md", "policy": {"approved": True, "allow_local_files": True}},
                {"source_id": "safe-audience", "source_type": "document", "uri": "audience.md", "policy": {"approved": True, "allow_local_files": True}},
            ]
        },
    )
    before_replay = len(backend.list_states())
    replay = service.execute(
        f"/continue {proposal.data['run_id']}",
        [],
        inputs={
            "research_sources": [
                {"source_id": "safe-category", "source_type": "document", "uri": "category.md", "policy": {"approved": True, "allow_local_files": True}},
                {"source_id": "safe-audience", "source_type": "document", "uri": "audience.md", "policy": {"approved": True, "allow_local_files": True}},
            ]
        },
    )
    if len(backend.list_states()) != before_replay or replay.data.get("run_id") != thesis.data.get("run_id"):
        raise RuntimeError("duplicate handoff was not idempotent")
    _approval(service, thesis.data["run_id"], thesis.data["approval_token"], "Strategy Thesis")
    weak = service.execute(f"/continue {thesis.data['run_id']}", [])
    if weak.data.get("blocker") != "quality_failed:growth_blueprint_quality_gate":
        raise RuntimeError("weak Growth Blueprint was not blocked")
    revision = service.execute(
        f"/reject {weak.data['run_id']} because the candidate is generic and fails competitor substitution",
        [],
        principal_id="matt:synthetic-certification",
    )
    if revision.data.get("status") != "active":
        raise RuntimeError("quality revision did not reopen the producing specialist")
    final_blueprint = service.execute(f"/continue {weak.data['run_id']}", [])
    if final_blueprint.data.get("status") != "awaiting_approval":
        raise RuntimeError("revised Blueprint did not reach human review")

    restarted_backend = FileWorkflowCommandBackend(root, dispatchers=dispatchers, environ={})
    restarted = TonyWorkflowCommandService(_Fallback(), restarted_backend)
    resumed = restarted.execute(f"/workflow {final_blueprint.data['run_id']}", [])
    if resumed.data.get("approval_token") != final_blueprint.data.get("approval_token"):
        raise RuntimeError("restart changed the exact-version approval token")
    _approval(
        restarted,
        final_blueprint.data["run_id"],
        resumed.data["approval_token"],
        "final Growth Blueprint",
    )

    states = _states(restarted_backend)
    blueprint = states["strategy_thesis_to_growth_blueprint"]
    candidate = blueprint.stage("prepare_growth_blueprint").output_artifacts[-1]
    directed_blueprint = blueprint.stage("direct_growth_blueprint").output_artifacts[-1]
    review = blueprint.stage("review_growth_blueprint").output_artifacts[-1]
    binding = blueprint.approval_history[-1]["approval_binding"]
    workflows = (
        "growth_diagnostic_to_blueprint_lite",
        "blueprint_lite_to_discovery_preparation",
        "discovery_evidence_to_growth_sprint_proposal",
        "growth_sprint_to_research_engine",
        "research_to_strategic_synthesis",
        "strategic_synthesis_to_strategy_thesis",
        "strategy_thesis_to_growth_blueprint",
    )
    missing = [item for item in workflows if item not in states]
    false_success = [
        state.run_id for state in states.values()
        if state.external_action_taken or state.external_action_receipts
    ]
    governed_artifacts = [
        artifact
        for workflow in workflows
        if workflow in states
        for stage in states[workflow].stages
        for artifact in stage.output_artifacts
    ]
    required_governance = {
        "workspace_id", "client_id", "workflow_id", "run_id", "stage_id",
        "version", "created_at", "source_input_fields", "generating_specialist",
        "provider", "quality_status", "approval_status", "revision_history",
    }
    governance_complete = bool(governed_artifacts) and all(
        required_governance.issubset(artifact.metadata) for artifact in governed_artifacts
    )
    passed = (
        not missing
        and not false_success
        and governance_complete
        and candidate.metadata.get("version") == 2
        and review.metadata.get("reviewed_artifact_checksum") == directed_blueprint.checksum
        and binding.get("reviewed_artifact_checksum") == directed_blueprint.checksum
        and blueprint.status.value == "complete"
        and blueprint.approval_status == "approved"
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    certification_id = (
        f"golden-path-{generated_at[:10].replace('-', '')}-{str(candidate.checksum)[:12]}"
    )
    report = {
        "title": "NARRATIIVE GOLDEN PATH CERTIFICATION",
        "certification_id": certification_id,
        "generated_at": generated_at,
        "status": "PASS" if passed else "FAIL",
        "fixture": {"client_id": CLIENT_ID, "company": COMPANY, "synthetic": True},
        "workflow_sequence": [
            {
                "workflow_id": item,
                "run_id": states[item].run_id,
                "status": states[item].status.value,
                "approval_status": states[item].approval_status,
                "artifact_ids": [
                    artifact.artifact_id
                    for stage in states[item].stages
                    for artifact in stage.output_artifacts
                ],
            }
            for item in workflows if item in states
        ],
        "quality_revision": {
            "failed_candidate_retained": bool(blueprint.stage("prepare_growth_blueprint").attempts[0].get("candidate_artifact")),
            "final_version": candidate.metadata.get("version"),
            "final_artifact_id": candidate.artifact_id,
            "final_checksum": candidate.checksum,
            "blueprint_director_artifact_id": directed_blueprint.artifact_id,
            "blueprint_director_checksum": directed_blueprint.checksum,
            "senior_review_artifact_id": review.artifact_id,
            "senior_review_bound_checksum": review.metadata.get("reviewed_artifact_checksum"),
        },
        "artifact_governance_complete": governance_complete,
        "acceptance_proofs": {
            "opportunity_entered": "growth_diagnostic_to_blueprint_lite" in states,
            "blueprint_lite_durable": "growth_diagnostic_to_blueprint_lite" in states,
            "version_bound_approval": bool(binding.get("reviewed_artifact_checksum")),
            "discovery_preparation_durable": "blueprint_lite_to_discovery_preparation" in states,
            "growth_sprint_proposal_durable": "discovery_evidence_to_growth_sprint_proposal" in states,
            "delivery_initiated": "growth_sprint_to_research_engine" in states,
            "research_durable": "growth_sprint_to_research_engine" in states,
            "strategic_synthesis_durable": "research_to_strategic_synthesis" in states,
            "strategy_thesis_durable": "strategic_synthesis_to_strategy_thesis" in states,
            "growth_blueprint_durable": "strategy_thesis_to_growth_blueprint" in states,
            "quality_failure_routed_to_revision": bool(
                blueprint.stage("prepare_growth_blueprint").attempts[0].get("candidate_artifact")
            ),
            "revision_created_new_version": candidate.metadata.get("version") == 2,
            "human_review_bound_final_version": binding.get("reviewed_artifact_checksum") == directed_blueprint.checksum,
            "restart_resume_preserved": True,
            "duplicate_execution_suppressed": True,
            "external_action_separately_gated": not false_success,
            "no_false_success": not false_success,
        },
        "exact_version_human_gate": binding,
        "restart_resume_preserved_token": True,
        "duplicate_execution_suppressed": True,
        "external_action_taken": False,
        "false_success_events": false_success,
        "missing_workflows": missing,
        "downstream_not_certified": ["Creative", "Media", "Measurement", "Client Operations"],
    }
    (root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated Narratiive Golden Path certification.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or (
        ROOT / ".runtime" / "golden-path-certification" /
        f"golden-path-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    report = run(output.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
