from __future__ import annotations

import json
import tempfile
import time
import unittest
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleRecord, ClientLifecycleStage
from runtime.campaign_world_triage_worker import CampaignWorldTriageWorker
from runtime.creative_bible_triage_worker import CreativeBibleTriageWorker
from runtime.inbound_leads import InboundLead
from runtime.inbound_lifecycle import project_inbound_lead
from runtime.models import WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.run_service import WorkflowRunService
from runtime.tony_blueprint_lite_inbound import TonyInboundBlueprintLiteService
from runtime.tony_workflow_runtime import TonyWorkflowRuntime
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    WorkerAvailability,
    WorkerMetadata,
    WorkerRegistration,
)
from runtime.workflow_execution_coordinator import FileWorkflowArtifactStore, WorkflowExecutionCoordinator
from runtime.deliverable_production import _checksum
from runtime.workflow_handoffs import build_next_workflow_inputs
from runtime.workflow_quality import (
    campaign_world_candidates_quality_gate,
    campaign_world_triage_quality_gate,
    creative_bible_quality_gate,
    creative_bible_triage_quality_gate,
    discovery_preparation_quality_gate,
    growth_blueprint_deliverable_quality_gate,
    growth_blueprint_quality_gate,
    growth_sprint_proposal_quality_gate,
    research_evidence_quality_gate,
)
from runtime.workflow_registry import WorkflowDefinition, build_narratiive_workflow_registry
from tests.test_tony_workflow_runtime import _blueprint_output
from tests.test_workflow_quality import (
    campaign_world_candidates_output,
    creative_bible_output,
    discovery_output,
    growth_blueprint_output,
    proposal_output,
)


CLIENT_NAME = "Northstar Test Co"
CLIENT_ID = "northstar-test-co-e2e"
WORKSPACE_ID = "northstar-test-workspace-e2e"
LEAD_ID = "northstar-test-lead-e2e"
CORRELATION_ID = "northstar-test-correlation-e2e"
RUN_PREFIX = "northstar-test-lifecycle"


def _campaign_identity() -> dict[str, Any]:
    return {
        "workspace_id": WORKSPACE_ID,
        "client_id": CLIENT_ID,
        "brand_id": "northstar-test-brand",
        "market_ids": ["uk-test-market"],
        "product_ids": ["northstar-test-product"],
        "campaign_id": "northstar-test-campaign",
    }


@dataclass(frozen=True, slots=True)
class GateEvidence:
    gate: str
    input_state: dict[str, Any]
    prerequisite_validation: dict[str, Any]
    dispatched_worker: str
    output_artefact: dict[str, Any]
    validation_result: dict[str, Any]
    resulting_state: dict[str, Any]
    audit_events: tuple[str, ...]
    elapsed_ms: float
    continuation_command: str
    status: str
    failure_reason: str = ""


def _lifecycle() -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=CLIENT_ID,
        client_name=CLIENT_NAME,
        stage=ClientLifecycleStage.BLUEPRINT_LITE,
        owner="Tony",
        next_action="Prepare the next internal Northstar Test Co lifecycle artefact.",
        evidence=("synthetic:northstar-test-co",),
        acquisition_path=AcquisitionPath.INBOUND,
    )


def _research_output() -> dict[str, Any]:
    return {
        "research_tasks": [{
            "task_id": "northstar-test-task-1",
            "question": "Which evidence should shape the synthetic growth choice?",
            "required_capability": "market_research",
            "assigned_worker": "northstar-test-fixture-worker",
        }],
        "evidence_pack": {
            "records": [{"evidence_id": "northstar-test-evidence-1"}],
            "sources": [{"policy": {"approved": True}}],
        },
        "source_provenance": [{
            "source_id": "northstar-test-source-1",
            "content_hash": "northstar-test-content-hash",
            "retrieved_at": "2026-09-17T00:00:00+00:00",
        }],
        "consolidated_findings": [{
            "statement": "Synthetic evidence indicates that clearer positioning merits testing.",
            "classification": "fact",
            "evidence_refs": ["northstar-test-evidence-1"],
            "source_refs": ["northstar-test-source-1"],
        }],
        "contradictions": [],
        "research_gaps": ["No real customer evidence is used in this isolated test."],
        "further_research_requests": [{
            "gap": "Real customer evidence",
            "status": "requires_additional_approved_source",
        }],
        "fact_interpretation_hypothesis_lineage": {
            "facts": [{"statement": "The fixture is synthetic."}],
            "interpretations": [{"statement": "The synthetic evidence suggests a positioning choice."}],
            "hypotheses": [{"statement": "A clearer synthetic position may improve response."}],
        },
        "external_action_taken": False,
    }


def _deliverable_output() -> dict[str, Any]:
    return {
        "presentation_specification": {"title": f"{CLIENT_NAME} Growth Blueprint", "slides": 30},
        "editable_pptx": "northstar-test-drive://growth-blueprint-v1.pptx",
        "review_pdf": "northstar-test-drive://growth-blueprint-v1.pdf",
        "visual_qa": {"status": "passed", "checks": {"fit": True, "legibility": True}},
        "proposed_client_release": {"status": "pending_human_approval"},
        "approval_status": "pending",
        "external_action_taken": False,
    }


def _fixture_output(workflow_id: str) -> dict[str, Any]:
    if workflow_id == "growth_diagnostic_to_blueprint_lite":
        return _blueprint_output()
    if workflow_id == "blueprint_lite_to_discovery_preparation":
        return discovery_output()
    if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
        return proposal_output()
    if workflow_id == "growth_sprint_to_research_engine":
        return _research_output()
    if workflow_id == "research_to_growth_blueprint":
        return growth_blueprint_output()
    if workflow_id == "growth_blueprint_deliverable_production":
        return _deliverable_output()
    if workflow_id == "growth_blueprint_to_campaign_world":
        return campaign_world_candidates_output()
    if workflow_id == "campaign_world_to_creative_bible":
        return creative_bible_output()
    if workflow_id == "creative_bible_to_asset_production":
        return {
            "production_tasks": [{"task_id": "northstar-test-asset-job-1", "status": "prepared"}],
            "asset_versions": [{"asset_id": "northstar-test-asset-1", "version": 1, "status": "in_review"}],
            "asset_manifest": {"manifest_id": "northstar-test-manifest-1", "version": 1},
            "production_gaps": ["No external production provider invoked by this test."],
            "external_action_taken": False,
        }
    if workflow_id == "asset_review_to_delivery_preparation":
        return {
            "delivery_package": {"package_id": "northstar-test-delivery-1", "status": "prepared"},
            "delivery_manifest": {"assets": ["northstar-test-asset-1-v1"]},
            "review_findings": ["Synthetic asset suite is structurally ready for human review."],
            "proposed_delivery_action": {"status": "pending_human_approval"},
            "external_action_taken": False,
        }
    if workflow_id == "delivery_to_follow_up_next_action":
        return {
            "recommended_follow_up": "Review synthetic delivery evidence and agree measurement timing.",
            "measurement_actions": ["Record baseline", "Review after synthetic observation period"],
            "draft_client_communication": "Synthetic draft only; do not send.",
            "external_action_taken": False,
        }
    raise AssertionError(f"unhandled registered workflow: {workflow_id}")


def _strict_fixture_validator(definition: WorkflowDefinition):
    required = definition.stages[0].output_contract.required_fields

    def validate(output: Mapping[str, Any]) -> Mapping[str, Any]:
        checks = {
            f"required_output:{field}": field in output and output[field] not in (None, "")
            for field in required
        }
        checks["no_external_action_taken"] = output.get("external_action_taken") is False
        failed = [name for name, passed in checks.items() if not passed]
        return {
            "passed": not failed,
            "failed_checks": failed,
            "checks": checks,
            "test_evidence_only": True,
            "production_validator_available": False,
        }

    return validate


def _build_runtime(root: Path, adapter=None) -> TonyWorkflowRuntime:
    registry = build_narratiive_workflow_registry()
    repository = FileWorkflowRunRepository(root / "runs", workspace_id=WORKSPACE_ID, client_id=CLIENT_ID)
    events = JsonlEventLog(root / "events", workspace_id=WORKSPACE_ID)
    runs = WorkflowRunService(repository, events, workspace_id=WORKSPACE_ID, client_id=CLIENT_ID)

    def fixture_worker(contract: dict[str, Any]) -> dict[str, Any]:
        if adapter is not None:
            return adapter(contract)
        output = _fixture_output(str(contract["workflow_context"]["workflow_id"]))
        # Fields declared as both handoff inputs and outputs are lineage-bearing
        # pass-through values. Preserve their exact value; the runtime correctly
        # rejects a worker that attempts to overwrite an upstream input.
        for field in contract["workflow_context"]["expected_outputs"]:
            if field in contract and field in output:
                output[field] = contract[field]
        return output

    workers = CapabilityWorkerRegistry((
        WorkerRegistration(
            WorkerMetadata(
                worker_id="northstar-test-fixture-worker",
                provider="isolated-deterministic-fixture",
                capabilities=(
                    "strategic_reasoning",
                    "copy_drafting",
                    "market_research",
                    "document_generation",
                    "creative_asset_production",
                ),
                availability=WorkerAvailability.AVAILABLE,
                side_effect_permissions=("preparation", "external_read"),
                max_attempts=1,
            ),
            fixture_worker,
        ),
        WorkerRegistration(
            WorkerMetadata(
                worker_id="northstar-test-tony-triage",
                provider="isolated-deterministic-fixture",
                capabilities=("creative_quality_triage",),
                availability=WorkerAvailability.AVAILABLE,
                side_effect_permissions=("preparation",),
                max_attempts=1,
            ),
            CampaignWorldTriageWorker(),
        ),
        WorkerRegistration(
            WorkerMetadata(
                worker_id="northstar-test-creative-bible-triage",
                provider="isolated-deterministic-fixture",
                capabilities=("creative_bible_quality_triage",),
                availability=WorkerAvailability.AVAILABLE,
                side_effect_permissions=("preparation",),
                max_attempts=1,
            ),
            CreativeBibleTriageWorker(),
        ),
    ))
    validators = {
        "blueprint_lite_quality_gate": TonyInboundBlueprintLiteService._quality_gate,
        "discovery_preparation_quality_gate": discovery_preparation_quality_gate,
        "growth_sprint_proposal_quality_gate": growth_sprint_proposal_quality_gate,
        "research_evidence_quality_gate": research_evidence_quality_gate,
        "growth_blueprint_quality_gate": growth_blueprint_quality_gate,
        "growth_blueprint_deliverable_quality_gate": growth_blueprint_deliverable_quality_gate,
        "campaign_world_candidates_quality_gate": campaign_world_candidates_quality_gate,
        "campaign_world_triage_quality_gate": campaign_world_triage_quality_gate,
        "creative_bible_quality_gate": creative_bible_quality_gate,
        "creative_bible_triage_quality_gate": creative_bible_triage_quality_gate,
    }
    for definition in registry.all():
        for stage in definition.stages:
            validators.setdefault(stage.quality_contract, _strict_fixture_validator(definition))
    coordinator = WorkflowExecutionCoordinator(
        registry=registry,
        workers=workers,
        runs=runs,
        artifacts=FileWorkflowArtifactStore(root / "artifacts"),
        quality_validators=validators,
    )
    return TonyWorkflowRuntime(
        coordinator=coordinator,
        runs=runs,
        business_projection=None,
    )


def _additional_inputs(workflow_id: str, prior_output: Mapping[str, Any]) -> dict[str, Any]:
    common_context = {"name": CLIENT_NAME, "source_ref": "synthetic:northstar-test-co"}
    values: dict[str, dict[str, Any]] = {
        "blueprint_lite_to_discovery_preparation": {},
        "discovery_evidence_to_growth_sprint_proposal": {
            "discovery_evidence": {
                "notes": "Synthetic Northstar Test Co discovery notes.",
                "sources": [{
                    "source_id": "northstar-test-discovery-notes",
                    "source_type": "notes",
                    "location": "synthetic:northstar-test-discovery",
                }],
            },
        },
        "growth_sprint_to_research_engine": {
            "research_sources": [{
                "source_id": "northstar-test-source-1",
                "source_type": "document",
                "uri": "synthetic:northstar-test-source",
                "policy": {"approved": True},
            }],
        },
        "research_to_growth_blueprint": {},
        "growth_blueprint_deliverable_production": {
            "quality_accepted_growth_blueprint": dict(prior_output),
            "blueprint_identity": {
                "artifact_id": "artifact-northstar-test-approved-blueprint",
                "version": 1,
                "checksum": _checksum(prior_output),
            },
            "client_context": common_context,
            "blueprint_canon": {"bundle": "synthetic-test-only", "checksum": "northstar-test-canon"},
        },
        "growth_blueprint_to_campaign_world": {
            "campaign_identity": _campaign_identity(),
            "approved_growth_blueprint": dict(prior_output),
        },
        "campaign_world_to_creative_bible": {
            "approved_campaign_world": campaign_world_candidates_output()["campaign_world_candidates"][0]["campaign_world"],
            "campaign_world_selection": {
                "approver": "matt-authorised-synthetic-e2e",
                "rationale": "Synthetic exact candidate selection.",
                "candidate_id": "northstar-world-1",
                "candidate_checksum": "synthetic-bound-in-runtime-chain",
            },
            "growth_blueprint": {"source": "northstar-test-approved-blueprint"},
            "production_context": {"channels": ["Meta", "TikTok", "Google"], "test_only": True},
        },
        "creative_bible_to_asset_production": {
            "asset_manifest": {"manifest_id": "northstar-test-manifest-1", "status": "planned"},
        },
        "asset_review_to_delivery_preparation": {
            "reviewed_assets": prior_output.get("asset_versions"),
            "delivery_requirements": {"repository": "isolated-test-fixture", "human_approval": True},
        },
        "delivery_to_follow_up_next_action": {
            "verified_delivery_evidence": prior_output.get("delivery_manifest"),
            "client_context": common_context,
            "measurement_context": {"status": "not_started", "test_only": True},
        },
    }
    return values[workflow_id]


def _latest_output(runtime: TonyWorkflowRuntime, run_id: str) -> dict[str, Any]:
    state = runtime.runs.load_run(run_id)
    if not state.stages[-1].output_artifacts:
        raise AssertionError(
            f"workflow {state.workflow_id} produced no accepted artefact: "
            f"status={state.status.value} blocker={state.blocker} "
            f"missing={state.stages[-1].missing_inputs} quality={state.stages[-1].quality_result}"
        )
    artefact = state.stages[-1].output_artifacts[-1]
    return json.loads(Path(artefact.location).read_text(encoding="utf-8"))


def _record_gate(runtime: TonyWorkflowRuntime, run_id: str, elapsed_ms: float) -> GateEvidence:
    state = runtime.runs.load_run(run_id)
    definition = runtime.coordinator.registry.resolve(state.workflow_id)
    stage = state.stages[0]
    required = definition.stages[0].input_contract.required_fields
    missing = [field for field in required if state.input_payload.get(field) in (None, "", [], {})]
    attempt = stage.attempts[-1] if stage.attempts else {}
    artefact = stage.output_artifacts[-1] if stage.output_artifacts else None
    human_gate = state.status is WorkflowStatus.AWAITING_APPROVAL
    if human_gate and state.workflow_id == "growth_blueprint_to_campaign_world":
        command = f"/approve {run_id} because candidate review accepted; /worlds {run_id}; /select-world {run_id} because <reason>; /continue {run_id}"
    elif human_gate and state.workflow_id == "campaign_world_to_creative_bible":
        command = f"/bible {run_id}; /approve-bible {run_id} because <reason>; /continue {run_id}"
    elif human_gate:
        command = f"/approve {run_id} because Northstar Test Co gate reviewed; then /continue {run_id}"
    else:
        command = f"/continue {run_id}" if definition.next_workflow_id else "No continuation: terminal next-action state"
    passed = not missing and stage.quality_result is not None and stage.quality_result.get("passed") is True
    return GateEvidence(
        gate=state.workflow_id,
        input_state={
            "run_id": run_id,
            "workflow_status_before_approval": state.status.value,
            "input_fields": sorted(state.input_payload),
        },
        prerequisite_validation={"required_fields": list(required), "missing_fields": missing, "passed": not missing},
        dispatched_worker=str(attempt.get("worker_id") or "none"),
        output_artefact=(
            {
                "artifact_id": artefact.artifact_id,
                "checksum": artefact.checksum,
                "location": Path(artefact.location).name,
                "parent_artifact_ids": artefact.metadata.get("parent_artifact_ids", []),
            }
            if artefact
            else {}
        ),
        validation_result=dict(stage.quality_result or {}),
        resulting_state={
            "status": state.status.value,
            "approval_status": state.approval_status,
            "external_action_taken": state.external_action_taken,
            "blocker": state.blocker,
        },
        audit_events=tuple(event.event_type for event in runtime.runs.event_log.read(run_id)),
        elapsed_ms=round(elapsed_ms, 3),
        continuation_command=command,
        status="PASS" if passed else "FAIL",
        failure_reason="" if passed else str(state.blocker or stage.quality_result or "gate did not complete"),
    )


def _ordered_definitions(runtime: TonyWorkflowRuntime) -> list[WorkflowDefinition]:
    definitions: list[WorkflowDefinition] = []
    workflow_id = "growth_diagnostic_to_blueprint_lite"
    while workflow_id:
        definition = runtime.coordinator.registry.resolve(workflow_id)
        definitions.append(definition)
        workflow_id = definition.next_workflow_id
    return definitions


def execute_all_gate_conformance(root: Path) -> tuple[TonyWorkflowRuntime, list[GateEvidence]]:
    runtime = _build_runtime(root)
    definitions = _ordered_definitions(runtime)
    first = definitions[0]
    run_id = f"{RUN_PREFIX}-{first.workflow_id}"
    runtime.enqueue(
        first.workflow_id,
        run_id,
        {
            "diagnostic_input_package": {
                "overall_score": 42,
                "main_blockage": "Synthetic positioning is deliberately indistinct.",
                "raw_answers": {"challenge": "Northstar Test Co fixture only"},
            },
            "company": CLIENT_NAME,
            "email": "northstar-test-co@acceptance.invalid",
        },
        entity_id=LEAD_ID,
        correlation_id=CORRELATION_ID,
    )
    records: list[GateEvidence] = []
    started = time.perf_counter()
    runtime.advance(run_id, _lifecycle())
    records.append(_record_gate(runtime, run_id, (time.perf_counter() - started) * 1000))

    for index, definition in enumerate(definitions):
        state = runtime.runs.load_run(run_id)
        if state.status is WorkflowStatus.AWAITING_APPROVAL:
            runtime.approve(
                run_id,
                approver="matt-authorised-synthetic-e2e",
                rationale=f"Approve isolated {CLIENT_NAME} gate for lifecycle testing only.",
                approval_binding={"test_fixture": CLIENT_ID, "artifact_checksum": state.stages[0].output_artifacts[-1].checksum},
            )
        if definition.workflow_id == "growth_blueprint_to_campaign_world":
            brief = runtime.campaign_world_selection_brief(run_id)
            selected = brief["candidates"][0]
            runtime.select_campaign_world(
                run_id,
                candidate_id=selected["candidate_id"],
                candidate_checksum=selected["candidate_checksum"],
                approver="matt-authorised-synthetic-e2e",
                rationale="Select exact isolated Campaign World candidate.",
            )
        if definition.workflow_id == "campaign_world_to_creative_bible":
            brief = runtime.creative_bible_approval_brief(run_id)
            runtime.approve_creative_bible(
                run_id,
                creative_bible_checksum=brief["creative_bible_checksum"],
                approver="matt-authorised-synthetic-e2e",
                rationale="Approve exact isolated Creative Bible version.",
            )
        if not definition.next_workflow_id:
            break
        prior_state = runtime.runs.load_run(run_id)
        prior_output = _latest_output(runtime, run_id)
        next_definition = definitions[index + 1]
        next_inputs = build_next_workflow_inputs(
            prior_state,
            prior_output,
            _additional_inputs(next_definition.workflow_id, prior_output),
        )
        if definition.workflow_id == "campaign_world_to_creative_bible":
            approval = next(
                item for item in reversed(prior_state.approval_history)
                if item.get("decision") == "creative_bible_approval"
            )
            next_inputs["approved_creative_bible"] = dict(prior_state.input_payload["creative_directors_bible"])
            next_inputs["creative_bible_approval"] = dict(approval)
        next_stage = next_definition.stages[0]
        for field in next_stage.output_contract.required_fields:
            if field not in next_stage.input_contract.required_fields:
                next_inputs.pop(field, None)
        next_run_id = f"{RUN_PREFIX}-gate-{index + 2:02d}"
        started = time.perf_counter()
        runtime.enqueue(
            next_definition.workflow_id,
            next_run_id,
            next_inputs,
            entity_id=LEAD_ID,
            correlation_id=CORRELATION_ID,
        )
        runtime.runs.record_handoff(
            run_id,
            next_workflow_id=next_definition.workflow_id,
            next_run_id=next_run_id,
        )
        outcome = runtime.advance(next_run_id, _lifecycle())
        run_id = next_run_id
        records.append(_record_gate(runtime, run_id, (time.perf_counter() - started) * 1000))
        if next_definition.workflow_id != outcome.workflow_id:
            raise AssertionError("registered workflow order and handoff chain diverged")
    return runtime, records


def execute_native_lifecycle_until_failure(root: Path) -> tuple[TonyWorkflowRuntime, list[str], Exception | None]:
    runtime = _build_runtime(root)
    definitions = _ordered_definitions(runtime)
    first = definitions[0]
    run_id = f"{RUN_PREFIX}-{first.workflow_id}"
    runtime.enqueue(
        first.workflow_id,
        run_id,
        {
            "diagnostic_input_package": {
                "overall_score": 42,
                "main_blockage": "Synthetic positioning is deliberately indistinct.",
                "raw_answers": {"challenge": "Northstar Test Co fixture only"},
            },
            "company": CLIENT_NAME,
            "email": "northstar-test-co@acceptance.invalid",
        },
        entity_id=LEAD_ID,
        correlation_id=CORRELATION_ID,
    )
    reached: list[str] = []
    runtime.advance(run_id, _lifecycle())
    reached.append(first.workflow_id)
    for index, definition in enumerate(definitions):
        state = runtime.runs.load_run(run_id)
        if state.status is WorkflowStatus.AWAITING_APPROVAL:
            runtime.approve(
                run_id,
                approver="matt-authorised-synthetic-e2e",
                rationale="Approve isolated native-chain test gate.",
            )
        if definition.workflow_id == "growth_blueprint_to_campaign_world":
            brief = runtime.campaign_world_selection_brief(run_id)
            selected = brief["candidates"][0]
            runtime.select_campaign_world(
                run_id,
                candidate_id=selected["candidate_id"],
                candidate_checksum=selected["candidate_checksum"],
                approver="matt-authorised-synthetic-e2e",
                rationale="Select exact isolated Campaign World candidate.",
            )
        if definition.workflow_id == "campaign_world_to_creative_bible":
            brief = runtime.creative_bible_approval_brief(run_id)
            runtime.approve_creative_bible(
                run_id,
                creative_bible_checksum=brief["creative_bible_checksum"],
                approver="matt-authorised-synthetic-e2e",
                rationale="Approve exact isolated Creative Bible version.",
            )
        if not definition.next_workflow_id:
            return runtime, reached, None
        output = _latest_output(runtime, run_id)
        try:
            outcome = runtime.handoff(
                run_id,
                _lifecycle(),
                _additional_inputs(definition.next_workflow_id, output),
            )
        except Exception as exc:  # Evidence capture: the failure type is asserted by the test.
            return runtime, reached, exc
        run_id = outcome.run_id
        reached.append(definitions[index + 1].workflow_id)
    return runtime, reached, None


class TonyFullLifecycleTest(unittest.TestCase):
    def test_synthetic_new_lead_enters_the_existing_inbound_lifecycle(self) -> None:
        lead = InboundLead(
            lead_id=LEAD_ID,
            contact="Northstar Test Contact",
            company=CLIENT_NAME,
            email="northstar-test-co@acceptance.invalid",
            source="Growth Diagnostic",
            status="New",
            pipeline_stage="New Diagnostic",
            lead_temperature="Warm",
            recommended_next_action="Prepare the synthetic Blueprint Lite evidence package.",
            notion_url="https://notion.invalid/northstar-test-co-e2e",
        )
        projected = project_inbound_lead(lead)
        self.assertEqual(projected.client_id, LEAD_ID)
        self.assertEqual(projected.client_name, CLIENT_NAME)
        self.assertEqual(projected.stage, ClientLifecycleStage.LEAD)
        self.assertEqual(projected.acquisition_path, AcquisitionPath.INBOUND)

    def test_northstar_test_co_traverses_every_registered_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="northstar-test-lifecycle-") as directory:
            runtime, records = execute_all_gate_conformance(Path(directory))
            expected: list[str] = []
            workflow_id = "growth_diagnostic_to_blueprint_lite"
            while workflow_id:
                expected.append(workflow_id)
                workflow_id = runtime.coordinator.registry.resolve(workflow_id).next_workflow_id
            self.assertEqual([item.gate for item in records], expected)
            self.assertEqual(len(records), 11)
            self.assertTrue(all(item.status == "PASS" for item in records), [asdict(item) for item in records])
            self.assertTrue(all(item.dispatched_worker in {"northstar-test-fixture-worker", "northstar-test-tony-triage"} for item in records))
            self.assertTrue(all(item.output_artefact for item in records))
            self.assertTrue(all("stage.completed" in item.audit_events for item in records))
            self.assertTrue(all(item.resulting_state["external_action_taken"] is False for item in records))
            final = runtime.runs.load_run(records[-1].input_state["run_id"])
            self.assertEqual(final.status, WorkflowStatus.COMPLETE)
            self.assertEqual(final.approval_status, "approved")

    def test_human_gates_halt_and_expose_explicit_continuation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="northstar-test-gates-") as directory:
            _runtime, records = execute_all_gate_conformance(Path(directory))
        gated = [item for item in records if item.resulting_state["status"] == "awaiting_approval"]
        self.assertEqual(len(gated), 10)
        self.assertTrue(all(item.resulting_state["approval_status"] == "pending" for item in gated))
        self.assertTrue(all(item.continuation_command.startswith("/") for item in gated))
        self.assertTrue(all(f"/continue {item.input_state['run_id']}" in item.continuation_command for item in gated))

    def test_native_continuous_chain_completes_with_bounded_run_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="northstar-test-native-chain-") as directory:
            runtime, reached, failure = execute_native_lifecycle_until_failure(Path(directory))
        self.assertIsNone(failure)
        self.assertEqual(reached, [definition.workflow_id for definition in _ordered_definitions(runtime)])

    def test_duplicate_intake_is_idempotent_and_conflicting_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="northstar-test-duplicate-") as directory:
            runtime = _build_runtime(Path(directory))
            payload = {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "synthetic"}}}
            first = runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", "northstar-test-duplicate", payload,
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            replay = runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", "northstar-test-duplicate", payload,
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            self.assertEqual(first["run_id"], replay["run_id"])
            self.assertEqual(
                [event.event_type for event in runtime.runs.event_log.read("northstar-test-duplicate")].count("workflow.created"),
                1,
            )
            with self.assertRaisesRegex(ValueError, "different inputs"):
                runtime.enqueue(
                    "growth_diagnostic_to_blueprint_lite", "northstar-test-duplicate",
                    {"diagnostic_input_package": {"overall_score": 99}},
                    entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
                )

    def test_missing_required_data_blocks_without_dispatch(self) -> None:
        calls: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="northstar-test-missing-") as directory:
            runtime = _build_runtime(Path(directory), adapter=lambda contract: calls.append(contract) or _blueprint_output())
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", "northstar-test-missing", {},
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            outcome = runtime.advance("northstar-test-missing", _lifecycle())
            state = runtime.runs.load_run("northstar-test-missing")
        self.assertEqual(outcome.status, "blocked")
        self.assertIn("diagnostic_input_package", state.stages[0].missing_inputs)
        self.assertEqual(calls, [])

    def test_worker_failure_exhausts_retry_policy_and_preserves_attempts(self) -> None:
        def fail(_contract):
            raise TimeoutError("northstar synthetic timeout")

        with tempfile.TemporaryDirectory(prefix="northstar-test-worker-failure-") as directory:
            runtime = _build_runtime(Path(directory), adapter=fail)
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", "northstar-test-worker-failure",
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "synthetic"}}},
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            outcome = runtime.advance("northstar-test-worker-failure", _lifecycle())
            state = runtime.runs.load_run("northstar-test-worker-failure")
        self.assertEqual(outcome.blocker, "worker_retry_policy_exhausted")
        self.assertEqual(len(state.stages[0].attempts), 2)
        self.assertTrue(all(item["error_code"] == "worker_timeout" for item in state.stages[0].attempts))

    def test_malformed_worker_output_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="northstar-test-malformed-") as directory:
            runtime = _build_runtime(Path(directory), adapter=lambda _contract: [])
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", "northstar-test-malformed",
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "synthetic"}}},
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            outcome = runtime.advance("northstar-test-malformed", _lifecycle())
        self.assertEqual(outcome.blocker, "worker_output_rejected:MalformedWorkerOutput")
        self.assertFalse(outcome.external_action_taken)

    def test_rejected_approval_retains_prior_artefact_and_requires_revision(self) -> None:
        calls = 0

        def revise(contract):
            nonlocal calls
            calls += 1
            output = _blueprint_output()
            if calls > 1:
                output["blueprint_lite"] += " Revised after explicit rejection."
            return output

        with tempfile.TemporaryDirectory(prefix="northstar-test-rejection-") as directory:
            runtime = _build_runtime(Path(directory), adapter=revise)
            run_id = "northstar-test-rejected-approval"
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", run_id,
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "synthetic"}}},
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            runtime.advance(run_id, _lifecycle())
            before = runtime.runs.load_run(run_id).stages[0].output_artifacts[0]
            runtime.reject_for_revision(run_id, reviewer="matt-synthetic-reviewer", rationale="Strengthen the test tension.")
            revised = runtime.advance(run_id, _lifecycle())
            after = runtime.runs.load_run(run_id)
        self.assertEqual(revised.status, "awaiting_approval")
        self.assertEqual(len(after.stages[0].output_artifacts), 2)
        self.assertEqual(after.stages[0].output_artifacts[0], before)
        self.assertNotEqual(after.stages[0].output_artifacts[1].checksum, before.checksum)

    def test_premature_handoff_is_rejected_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="northstar-test-premature-") as directory:
            runtime = _build_runtime(Path(directory))
            run_id = "northstar-test-premature"
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite", run_id,
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "synthetic"}}},
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            runtime.advance(run_id, _lifecycle())
            with self.assertRaisesRegex(ValueError, "complete before handoff"):
                runtime.handoff(run_id, _lifecycle())
            self.assertEqual(runtime.runs.load_run(run_id).approval_status, "pending")

    def test_service_restart_preserves_gate_and_does_not_duplicate_execution(self) -> None:
        calls: list[str] = []

        def worker(contract):
            calls.append(str(contract["workflow_context"]["idempotency_key"]))
            return _blueprint_output()

        with tempfile.TemporaryDirectory(prefix="northstar-test-restart-") as directory:
            root = Path(directory)
            first = _build_runtime(root, adapter=worker)
            run_id = "northstar-test-restart"
            first.enqueue(
                "growth_diagnostic_to_blueprint_lite", run_id,
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "synthetic"}}},
                entity_id=LEAD_ID, correlation_id=CORRELATION_ID,
            )
            first.advance(run_id, _lifecycle())
            restarted = _build_runtime(root, adapter=worker)
            self.assertEqual(restarted.recover_pending(), 0)
            outcome = restarted.advance(run_id, _lifecycle())
            state = restarted.runs.load_run(run_id)
        self.assertEqual(outcome.status, "awaiting_approval")
        self.assertEqual(state.approval_status, "pending")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(state.stages[0].output_artifacts), 1)


if __name__ == "__main__":
    unittest.main()
