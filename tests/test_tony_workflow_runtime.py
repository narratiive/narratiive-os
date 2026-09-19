from __future__ import annotations

import hashlib
import json
import tempfile
import unittest

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_workflow_quality import (
    campaign_world_output,
    campaign_world_candidates_output,
    campaign_identity,
    creative_bible_output,
    discovery_output,
    growth_blueprint_output,
    proposal_output,
)


def _lifecycle(client_id: str) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name="SAFE Synthetic Company",
        stage=ClientLifecycleStage.LEAD,
        owner="Tony",
        next_action="Prepare the next internal work product",
        evidence=("synthetic:test",),
    )


def _blueprint_output() -> dict[str, object]:
    return {
        "blueprint_lite": "A substantive evidence-disciplined Blueprint Lite with a clear growth argument.",
        "diagnostic_signals_used": ["Overall score", "Main blockage", "Raw answer evidence"],
        "diagnostic_input_coverage": {"complete": True},
        "source_backed_evidence": [{"source": "https://example.com", "fact": "Reserved example domain"}],
        "evidence_gaps": ["Real company context is intentionally absent from this synthetic test."],
        "fact_interpretation_hypothesis_lineage": {
            "fact": ["The supplied diagnostic reports a blockage."],
            "interpretation": ["The blockage may be constraining demand."],
            "hypothesis": ["A clearer position could improve response."],
        },
        "growth_tension": "The company needs growth while its message remains indistinct.",
        "provisional_opportunity": "Test one sharper evidence-led position before scaling activity.",
        "questions_to_answer_next": [
            "Which segment responds best?",
            "What evidence predicts choice?",
            "Where does the current message fail?",
        ],
        "quality_gate": {"human_review_ready": True},
        "recommendation": "advance",
    }


def _production_output(contract: dict[str, object]) -> dict[str, object]:
    manifest = contract["asset_manifest"]
    manifest_checksum = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    versions = []
    receipts = []
    for index, asset in enumerate(manifest["assets"], start=1):
        version_id = f"{asset['asset_id']}-v1"
        versions.append(
            {
                "asset_version_id": version_id,
                "asset_id": asset["asset_id"],
                "production_job_id": asset["production_job_id"],
                "file_checksum": hashlib.sha256(version_id.encode("utf-8")).hexdigest(),
                "drive_uri": f"https://drive.google.invalid/{version_id}",
                "source_manifest_checksum": manifest_checksum,
                "version_number": 1,
                "status": "generated",
                "approval_status": "pending",
                "human_review_required": True,
                "delivery_authorised": False,
                "publication_authorised": False,
            }
        )
        receipts.append(
            {
                "asset_version_id": version_id,
                "provider_receipt_id": f"provider-receipt-{index}",
                "status": "complete",
            }
        )
    return {
        "asset_versions": versions,
        "production_receipts": receipts,
        "external_action_taken": True,
        "external_action_receipt": {"provider_batch_id": "safe-production-batch", "status": "complete"},
        "delivery_authorised": False,
        "publication_authorised": False,
        "media_spend_authorised": False,
    }


class TonyWorkflowRuntimeIntegrationTests(unittest.TestCase):
    def test_blueprint_lite_executes_through_registered_generic_runtime_and_pauses(self) -> None:
        calls = []

        def claude(contract):
            calls.append(contract)
            return _blueprint_output()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": claude},
                environ={},
            )
            registry_ids = {item.workflow_id for item in runtime.coordinator.registry.all()}
            self.assertEqual(len(registry_ids), 11)
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-blueprint-run",
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "safe"}}},
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-blueprint-run", _lifecycle("safe-client"))
            self.assertEqual(outcome.status, "awaiting_approval")
            self.assertEqual(outcome.action, "await_human_approval")
            self.assertFalse(outcome.external_action_taken)
            state = runtime.status("safe-blueprint-run")
            self.assertEqual(state["approval_status"], "pending")
            self.assertTrue(state["stages"][0]["quality_result"]["passed"])
            self.assertEqual(len(state["stages"][0]["output_artifacts"]), 1)
            self.assertEqual(calls[0]["worker"], "Claude")
            self.assertEqual(calls[0]["execution_mode"], "autonomous_prepare")

            restarted = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": claude},
                environ={},
            )
            self.assertEqual(restarted.status("safe-blueprint-run")["approval_status"], "pending")
            restarted.approve(
                "safe-blueprint-run",
                approver="authorised-human",
                rationale="Synthetic integration test only",
            )
            self.assertEqual(restarted.status("safe-blueprint-run")["status"], "complete")
            self.assertEqual(len(calls), 1)

    def test_discovery_preparation_uses_real_validator_and_pauses_for_review(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": lambda contract: calls.append(contract) or discovery_output()},
                environ={},
            )
            runtime.enqueue(
                "blueprint_lite_to_discovery_preparation",
                "safe-discovery-run",
                {
                    "blueprint_lite": "A substantive SAFE synthetic Blueprint Lite.",
                    "diagnostic_evidence": {"source": "synthetic"},
                    "company_context": {"name": "SAFE Synthetic Company"},
                },
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-discovery-run", _lifecycle("safe-client"))
            self.assertEqual(outcome.status, "awaiting_approval")
            self.assertTrue(runtime.status("safe-discovery-run")["stages"][0]["quality_result"]["passed"])
            self.assertEqual(len(calls), 1)
            self.assertFalse(outcome.external_action_taken)

    def test_discovery_evidence_produces_quality_gated_proposal_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": lambda contract: proposal_output()},
                environ={},
            )
            runtime.enqueue(
                "discovery_evidence_to_growth_sprint_proposal",
                "safe-proposal-run",
                {
                    "discovery_evidence": {
                        "notes": "SAFE synthetic discovery notes with unresolved questions.",
                        "sources": [{"source_id": "meeting-1", "source_type": "notes", "location": "meeting:synthetic"}],
                    },
                    "blueprint_lite": "A substantive SAFE synthetic Blueprint Lite.",
                    "commercial_context": {"company": "SAFE Synthetic Company"},
                },
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-proposal-run", _lifecycle("safe-client"))

            state = runtime.status("safe-proposal-run")
            self.assertEqual(outcome.status, "awaiting_approval")
            self.assertTrue(state["stages"][0]["quality_result"]["passed"])
            self.assertEqual(state["approval_status"], "pending")
            self.assertFalse(state["external_action_taken"])

    def test_campaign_world_uses_real_validator_and_requires_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": lambda contract: campaign_world_candidates_output()},
                environ={},
            )
            lineage = campaign_world_output()["evidence_lineage"]
            runtime.enqueue(
                "growth_blueprint_to_campaign_world",
                "safe-campaign-world-run",
                {
                    "campaign_identity": campaign_identity(),
                    "approved_growth_blueprint": {"status": "approved", "source": "synthetic"},
                    "evidence_lineage": lineage,
                    "activation_implications": {"priority": "Synthetic internal test"},
                },
                entity_id="safe-campaign",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-campaign-world-run", _lifecycle("safe-client"))
            state = runtime.status("safe-campaign-world-run")

            self.assertEqual(outcome.status, "awaiting_approval")
            self.assertEqual(outcome.action, "await_human_approval")
            self.assertTrue(state["stages"][0]["quality_result"]["passed"])
            self.assertTrue(state["stages"][1]["quality_result"]["passed"])
            self.assertEqual(state["stages"][1]["agent_ref"], "capability:creative_quality_triage")
            self.assertEqual(state["approval_status"], "pending")
            self.assertFalse(state["external_action_taken"])

            runtime.approve(
                "safe-campaign-world-run",
                approver="telegram:matt",
                rationale="Approve the exact candidate review set.",
            )
            brief = runtime.campaign_world_selection_brief("safe-campaign-world-run")
            self.assertEqual(len(brief["ready_candidate_ids"]), 3)
            selected = brief["candidates"][0]
            with self.assertRaisesRegex(ValueError, "Matt"):
                runtime.select_campaign_world(
                    "safe-campaign-world-run",
                    candidate_id=selected["candidate_id"],
                    candidate_checksum=selected["candidate_checksum"],
                    approver="tony",
                    rationale="Tony must never substitute for Matt.",
                )
            with self.assertRaisesRegex(ValueError, "stale"):
                runtime.select_campaign_world(
                    "safe-campaign-world-run",
                    candidate_id=selected["candidate_id"],
                    candidate_checksum="0" * 64,
                    approver="telegram:matt",
                    rationale="Stale selection test.",
                )
            runtime.select_campaign_world(
                "safe-campaign-world-run",
                candidate_id=selected["candidate_id"],
                candidate_checksum=selected["candidate_checksum"],
                approver="telegram:matt",
                rationale="Select this exact route for Creative Bible development.",
            )
            selected_state = runtime.runs.load_run("safe-campaign-world-run")
            self.assertEqual(selected_state.approval_history[-1]["decision"], "campaign_world_selection")
            self.assertFalse(selected_state.external_action_taken)

    def test_creative_bible_uses_real_validator_and_requires_human_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": lambda contract: creative_bible_output()},
                environ={},
            )
            runtime.enqueue(
                "campaign_world_to_creative_bible",
                "safe-creative-bible-run",
                {
                    "campaign_identity": campaign_identity(),
                    "approved_campaign_world": {"status": "approved", "source": "synthetic"},
                    "campaign_world_selection": {
                        "approver": "telegram:matt",
                        "rationale": "Synthetic exact Campaign World selection.",
                        "candidate_id": "safe-candidate-1",
                        "candidate_checksum": "safe-candidate-checksum",
                    },
                    "growth_blueprint": {"status": "approved", "source": "synthetic"},
                    "production_context": {"market": "Synthetic UK test market"},
                },
                entity_id="safe-campaign",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-creative-bible-run", _lifecycle("safe-client"))
            state = runtime.status("safe-creative-bible-run")

            self.assertEqual(outcome.status, "awaiting_approval")
            self.assertEqual(outcome.action, "await_human_approval")
            self.assertTrue(state["stages"][0]["quality_result"]["passed"])
            self.assertTrue(state["stages"][1]["quality_result"]["passed"])
            self.assertEqual(state["stages"][1]["agent_ref"], "capability:creative_bible_quality_triage")
            self.assertEqual(state["approval_status"], "pending")
            self.assertFalse(state["external_action_taken"])

            runtime.approve(
                "safe-creative-bible-run",
                approver="telegram:matt",
                rationale="Approve Tony's exact review gate.",
            )
            brief = runtime.creative_bible_approval_brief("safe-creative-bible-run")
            self.assertEqual(brief["tony_disposition"], "forward")
            with self.assertRaisesRegex(ValueError, "Matt"):
                runtime.approve_creative_bible(
                    "safe-creative-bible-run",
                    creative_bible_checksum=brief["creative_bible_checksum"],
                    approver="tony",
                    rationale="Tony must not approve the Bible.",
                )
            with self.assertRaisesRegex(ValueError, "stale"):
                runtime.approve_creative_bible(
                    "safe-creative-bible-run",
                    creative_bible_checksum="0" * 64,
                    approver="telegram:matt",
                    rationale="Stale approval test.",
                )
            runtime.approve_creative_bible(
                "safe-creative-bible-run",
                creative_bible_checksum=brief["creative_bible_checksum"],
                approver="telegram:matt",
                rationale="Approve this exact Bible for production planning.",
            )
            approved = runtime.runs.load_run("safe-creative-bible-run")
            self.assertEqual(approved.approval_history[-1]["decision"], "creative_bible_approval")
            self.assertFalse(approved.external_action_taken)

    def test_asset_production_planning_precedes_separate_provider_execution_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bible = creative_bible_output()["creative_directors_bible"]
            checksum = hashlib.sha256(
                json.dumps(bible, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={},
                environ={},
            )
            runtime.enqueue(
                "creative_bible_to_asset_production",
                "safe-production-run",
                {
                    "campaign_identity": campaign_identity(),
                    "approved_creative_bible": bible,
                    "creative_bible_approval": {
                        "decision": "creative_bible_approval",
                        "approver": "telegram:matt",
                        "rationale": "Exact Bible approved.",
                        "creative_bible_checksum": checksum,
                    },
                    "production_constraints": ["No publication", "Human review required"],
                },
                entity_id="safe-campaign",
                correlation_id="safe-correlation",
            )

            planned = runtime.advance("safe-production-run", _lifecycle("safe-client"))
            state = runtime.status("safe-production-run")

            self.assertEqual(planned.status, "awaiting_approval")
            self.assertTrue(state["stages"][0]["quality_result"]["passed"])
            self.assertEqual(state["stages"][0]["agent_ref"], "capability:production_planning")
            self.assertEqual(state["stages"][1]["status"], "ready")
            self.assertFalse(state["external_action_taken"])

            runtime.approve(
                "safe-production-run",
                approver="telegram:matt",
                rationale="Approve the exact internal Production Pack.",
            )
            execution_gate = runtime.advance("safe-production-run", _lifecycle("safe-client"))
            self.assertEqual(execution_gate.status, "awaiting_approval")
            self.assertIn("external action", execution_gate.proposed_next_action)
            self.assertFalse(execution_gate.external_action_taken)

    def test_every_generated_asset_version_requires_exact_matt_approval_before_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bible = creative_bible_output()["creative_directors_bible"]
            checksum = hashlib.sha256(
                json.dumps(bible, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Creative Production": _production_output},
                environ={},
            )
            runtime.enqueue(
                "creative_bible_to_asset_production",
                "safe-production-approval-run",
                {
                    "campaign_identity": campaign_identity(),
                    "approved_creative_bible": bible,
                    "creative_bible_approval": {
                        "decision": "creative_bible_approval",
                        "approver": "telegram:matt",
                        "rationale": "Exact Bible approved.",
                        "creative_bible_checksum": checksum,
                    },
                    "production_constraints": ["No publication", "Human review required"],
                },
                entity_id="safe-campaign",
                correlation_id="safe-correlation",
            )

            runtime.advance("safe-production-approval-run", _lifecycle("safe-client"))
            runtime.approve(
                "safe-production-approval-run",
                approver="telegram:matt",
                rationale="Approve the exact Production Pack.",
            )
            runtime.advance("safe-production-approval-run", _lifecycle("safe-client"))
            runtime.approve(
                "safe-production-approval-run",
                approver="telegram:matt",
                rationale="Approve provider execution for this exact Production Pack.",
            )
            produced = runtime.advance("safe-production-approval-run", _lifecycle("safe-client"))
            self.assertEqual(produced.status, "awaiting_approval", produced.blocker)
            runtime.approve(
                "safe-production-approval-run",
                approver="telegram:matt",
                rationale="Accept the completed production stage for review.",
            )
            runtime.advance("safe-production-approval-run", _lifecycle("safe-client"))

            brief = runtime.asset_suite_approval_brief("safe-production-approval-run")
            self.assertEqual(brief["asset_count"], 18)
            self.assertFalse(brief["delivery_authorised"])
            with self.assertRaisesRegex(ValueError, "Matt"):
                runtime.approve_asset_suite(
                    "safe-production-approval-run",
                    asset_suite_checksum=brief["asset_suite_checksum"],
                    approver="tony",
                    rationale="Tony cannot approve the suite.",
                )
            with self.assertRaisesRegex(ValueError, "stale"):
                runtime.approve_asset_suite(
                    "safe-production-approval-run",
                    asset_suite_checksum="0" * 64,
                    approver="telegram:matt",
                    rationale="Reject stale evidence.",
                )
            runtime.approve_asset_suite(
                "safe-production-approval-run",
                asset_suite_checksum=brief["asset_suite_checksum"],
                approver="telegram:matt",
                rationale="Approve every exact generated version for delivery preparation only.",
            )
            state = runtime.runs.load_run("safe-production-approval-run")
            decision = state.approval_history[-1]
            self.assertEqual(decision["decision"], "asset_suite_approval")
            self.assertEqual(len(decision["asset_version_ids"]), 18)
            self.assertFalse(decision["delivery_authorised"])
            self.assertFalse(decision["publication_authorised"])
            self.assertFalse(decision["media_spend_authorised"])

    def test_workspace_client_scopes_are_durably_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="client-one",
                dispatchers={},
                environ={},
            )
            second = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="client-two",
                dispatchers={},
                environ={},
            )
            first.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "shared-run-id",
                {"diagnostic_input_package": {"safe": "one"}},
                entity_id="lead-one",
                correlation_id="corr-one",
            )
            second.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "shared-run-id",
                {"diagnostic_input_package": {"safe": "two"}},
                entity_id="lead-two",
                correlation_id="corr-two",
            )
            self.assertEqual(first.status("shared-run-id")["entity_id"], "lead-one")
            self.assertEqual(second.status("shared-run-id")["entity_id"], "lead-two")

    def test_explicit_approved_handoffs_progress_blueprint_to_discovery_to_proposal(self) -> None:
        def claude(contract):
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if workflow_id == "growth_diagnostic_to_blueprint_lite":
                return _blueprint_output()
            if workflow_id == "blueprint_lite_to_discovery_preparation":
                return discovery_output()
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                return proposal_output()
            raise AssertionError(workflow_id)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": claude},
                environ={},
            )
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-commercial-chain",
                {
                    "diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "safe"}},
                    "company": "SAFE Commercial Chain Test",
                },
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            runtime.advance("safe-commercial-chain", _lifecycle("safe-client"))
            runtime.approve("safe-commercial-chain", approver="authorised-human", rationale="SAFE test approval")

            discovery = runtime.handoff("safe-commercial-chain", _lifecycle("safe-client"))
            self.assertEqual(discovery.workflow_id, "blueprint_lite_to_discovery_preparation")
            self.assertEqual(discovery.status, "awaiting_approval")
            discovery_run = "safe-commercial-chain-blueprint_lite_to_discovery_preparation"
            runtime.approve(discovery_run, approver="authorised-human", rationale="SAFE test approval")
            with self.assertRaisesRegex(ValueError, "discovery_evidence"):
                runtime.handoff(discovery_run, _lifecycle("safe-client"))

            proposal = runtime.handoff(
                discovery_run,
                _lifecycle("safe-client"),
                {
                    "discovery_evidence": {
                        "notes": "SAFE synthetic discovery notes with unresolved questions.",
                        "sources": [{"source_id": "meeting-1", "source_type": "notes", "location": "meeting:synthetic"}],
                    }
                },
            )
            self.assertEqual(proposal.workflow_id, "discovery_evidence_to_growth_sprint_proposal")
            self.assertEqual(proposal.status, "awaiting_approval")
            proposal_state = runtime.status(proposal.run_id)
            parent_ids = proposal_state["stages"][0]["output_artifacts"][0]["metadata"]["parent_artifact_ids"]
            self.assertTrue(parent_ids)
            self.assertFalse(proposal_state["external_action_taken"])

    def test_approved_blueprint_handoff_binds_exact_artefact_identity_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": lambda contract: growth_blueprint_output()},
                environ={},
            )
            runtime.enqueue(
                "research_to_growth_blueprint",
                "safe-growth-blueprint-run",
                {
                    "evidence_pack": {"records": [{"source_id": "safe-source"}]},
                    "approved_growth_sprint_scope": ["SAFE bounded workstream"],
                    "client_context": {"name": "Northstar Test Co"},
                },
                entity_id="safe-client",
                correlation_id="safe-correlation",
            )
            runtime.advance("safe-growth-blueprint-run", _lifecycle("safe-client"))
            runtime.approve(
                "safe-growth-blueprint-run",
                approver="authorised-human",
                rationale="SAFE synthetic Blueprint approval",
            )

            outcome = runtime.handoff("safe-growth-blueprint-run", _lifecycle("safe-client"))
            downstream = runtime.runs.load_run(outcome.run_id)
            source = runtime.runs.load_run("safe-growth-blueprint-run")
            source_ref = source.stages[0].output_artifacts[-1]

            self.assertEqual(outcome.workflow_id, "growth_blueprint_deliverable_production")
            self.assertEqual(outcome.status, "blocked")
            self.assertEqual(downstream.input_payload["blueprint_identity"]["artifact_id"], source_ref.artifact_id)
            self.assertEqual(downstream.input_payload["blueprint_identity"]["checksum"], source_ref.checksum)
            self.assertEqual(
                downstream.input_payload["quality_accepted_growth_blueprint"]["recommendation"],
                "advance",
            )
            self.assertEqual(
                downstream.input_payload["blueprint_canon"]["status"],
                "quality_accepted_and_human_approved",
            )
            self.assertFalse(downstream.external_action_taken)


if __name__ == "__main__":
    unittest.main()
