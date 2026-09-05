from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_workflow_quality import discovery_output, growth_blueprint_output, proposal_output


class FallbackCommands:
    def execute(self, command, objects):
        return CommandResponse("fallback", "healthy", "fallback", {})


def lifecycle(client_id: str) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name="SAFE Executive Workflow Test",
        stage=ClientLifecycleStage.RESEARCH,
        owner="Tony",
        next_action="Prepare internal work",
        evidence=("synthetic:test",),
    )


def blueprint_output() -> dict:
    return {
        "blueprint_lite": "A substantive synthetic Blueprint Lite with a clear strategic point of view.",
        "diagnostic_signals_used": ["overall score", "main blockage"],
        "diagnostic_input_coverage": {"complete": True},
        "source_backed_evidence": [{"source": "https://example.invalid", "fact": "Synthetic evidence"}],
        "evidence_gaps": ["Customer interviews are not yet available"],
        "fact_interpretation_hypothesis_lineage": {
            "fact": ["Synthetic fact"],
            "interpretation": ["Synthetic interpretation"],
            "hypothesis": ["Synthetic hypothesis"],
        },
        "growth_tension": "Demand exists but the proposition is unclear.",
        "provisional_opportunity": "Clarify the category entry point.",
        "questions_to_answer_next": ["Who buys?", "Why now?", "Why this?"],
        "quality_gate": {"human_review_ready": True},
        "recommendation": "advance",
    }


class TonyWorkflowCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.calls = []
        def claude(contract):
            self.calls.append(contract)
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if workflow_id == "blueprint_lite_to_discovery_preparation":
                return discovery_output()
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                return proposal_output()
            if workflow_id == "research_to_growth_blueprint":
                return growth_blueprint_output()
            return blueprint_output()

        self.dispatchers = {"Claude": claude}
        self.runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=self.dispatchers,
            environ={},
        )
        self.runtime.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            "safe-executive-run",
            {
                "diagnostic_input_package": {"overall_score": 40},
                "company": "SAFE Executive Workflow Test",
            },
            entity_id="safe-lead",
            correlation_id="safe-correlation",
        )
        self.runtime.advance("safe-executive-run", lifecycle("safe-client"))
        self.service = TonyWorkflowCommandService(
            FallbackCommands(),
            FileWorkflowCommandBackend(self.root, dispatchers=self.dispatchers, environ={}),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_status_and_queues_report_persisted_truth_concisely(self) -> None:
        status = self.service.execute("/workflow SAFE Executive Workflow Test", [])
        approvals = self.service.execute("/approvals", [])
        artefact = self.service.execute("/artefact safe-executive-run", [])

        self.assertEqual(status.data["status"], "awaiting_approval")
        self.assertTrue(status.data["approval_required"])
        self.assertFalse(status.data["external_action_taken"])
        self.assertEqual(len(approvals.data["runs"]), 1)
        self.assertIn("blueprint_lite", artefact.data["artefact_fields"])
        self.assertNotIn("input_payload", status.data)

    def test_approval_requires_authenticated_principal_and_rationale(self) -> None:
        denied = self.service.execute(
            "/approve safe-executive-run because reviewed synthetic work",
            [],
        )
        missing_reason = self.service.execute(
            "/approve safe-executive-run",
            [],
            principal_id="telegram:123",
        )
        approved = self.service.execute(
            "/approve safe-executive-run because reviewed synthetic work",
            [],
            principal_id="telegram:123",
        )

        self.assertEqual(denied.data["error_code"], "authorised_principal_required")
        self.assertEqual(missing_reason.data["error_code"], "rationale_required")
        self.assertEqual(approved.data["approval_status"], "approved")
        self.assertEqual(approved.data["status"], "complete")
        self.assertIsNone(approved.data["proposed_next_action"])
        self.assertFalse(approved.data["external_action_taken"])

        proposed = self.service.execute("/proposed safe-executive-run", [])
        self.assertIn("No current proposed next action", proposed.message)

    def test_legacy_approved_snapshot_does_not_present_approved_action_as_current(self) -> None:
        self.service.execute(
            "/approve safe-executive-run because reviewed synthetic work",
            [],
            principal_id="telegram:123",
        )
        state = self.runtime.runs.load_run("safe-executive-run")
        approved_action = state.approval_history[-1]["proposed_next_action"]
        state.proposed_next_action = approved_action
        self.runtime.runs.repository.save(state)

        status = self.service.execute("/workflow safe-executive-run", [])
        projection = self.service.execute("/projection safe-executive-run", [])

        self.assertIsNone(status.data["proposed_next_action"])
        self.assertNotIn(" Next:", status.message)
        self.assertIsNone(projection.data["proposed_next_action"])

    def test_rejection_reopens_exact_producing_step_without_deleting_artefact(self) -> None:
        rejected = self.service.execute(
            "/reject safe-executive-run because strengthen the evidence",
            [],
            principal_id="telegram:123",
        )
        state = self.runtime.status("safe-executive-run")

        self.assertEqual(rejected.data["status"], "active")
        self.assertEqual(state["stages"][0]["status"], "ready")
        self.assertEqual(state["stages"][0]["revision_count"], 1)
        self.assertEqual(len(state["stages"][0]["output_artifacts"]), 1)
        self.assertEqual(state["approval_history"][-1]["reviewer"], "telegram:123")

    def test_rejection_opens_new_attempt_budget_for_quality_blocked_work(self) -> None:
        def weak_blueprint(_contract):
            return {"blueprint_lite": "Too weak"}

        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-quality-client",
            dispatchers={"Claude": weak_blueprint},
            environ={},
        )
        runtime.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            "safe-quality-blocked-run",
            {
                "diagnostic_input_package": {"overall_score": 40},
                "company": "SAFE Quality Revision Test",
            },
            entity_id="safe-quality-lead",
            correlation_id="safe-quality-correlation",
        )
        blocked = runtime.advance("safe-quality-blocked-run", lifecycle("safe-quality-client"))
        service = TonyWorkflowCommandService(
            FallbackCommands(),
            FileWorkflowCommandBackend(
                self.root,
                dispatchers={"Claude": weak_blueprint},
                environ={},
            ),
        )

        revised = service.execute(
            "/reject safe-quality-blocked-run because revise the quality-rejected draft",
            [],
            principal_id="telegram:123",
        )
        state = runtime.status("safe-quality-blocked-run")

        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(revised.data["status"], "active")
        self.assertEqual(state["stages"][0]["status"], "ready")
        self.assertEqual(state["stages"][0]["revision_count"], 1)
        self.assertEqual(state["approval_history"][-1]["decision"], "request_revision")

    def test_ambiguous_company_reference_fails_safe(self) -> None:
        second = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client-two",
            dispatchers={},
            environ={},
        )
        second.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            "safe-executive-run-two",
            {"diagnostic_input_package": {"overall_score": 50}, "company": "SAFE Executive Workflow Test"},
            entity_id="safe-lead-two",
            correlation_id="safe-correlation-two",
        )

        response = self.service.execute("/workflow SAFE Executive Workflow Test", [])

        self.assertEqual(response.status, "error")
        self.assertIn("ambiguous", response.message)

    def test_non_workflow_command_delegates(self) -> None:
        response = self.service.execute("/health", [])
        self.assertEqual(response.command, "fallback")

    def test_notion_projection_requires_exact_approval_and_is_idempotent(self) -> None:
        calls = []

        def notion(dispatch):
            calls.append(dispatch)
            return {
                "external_action_taken": True,
                "record_id": "safe-notion-record",
                "projection_key": dispatch["idempotency_key"],
            }

        service = TonyWorkflowCommandService(
            FallbackCommands(),
            FileWorkflowCommandBackend(
                self.root,
                dispatchers={**self.dispatchers, "Notion": notion},
                environ={},
            ),
        )

        denied = service.execute("/sync-notion safe-executive-run because SAFE test", [])
        synced = service.execute(
            "/sync-notion safe-executive-run because SAFE test",
            [],
            principal_id="telegram:123",
        )
        replay = service.execute(
            "/sync-notion safe-executive-run because SAFE replay",
            [],
            principal_id="telegram:123",
        )

        self.assertEqual(denied.data["error_code"], "authorised_principal_required")
        self.assertEqual(synced.data["projection_status"], "verified")
        self.assertEqual(replay.data["projection_status"], "duplicate_suppressed")
        self.assertEqual(len(calls), 1)

    def test_continue_can_supply_provenanced_discovery_evidence_to_next_workflow(self) -> None:
        self.service.execute(
            "/approve safe-executive-run because reviewed Blueprint Lite",
            [],
            principal_id="telegram:123",
        )
        discovery = self.service.execute("/continue safe-executive-run", [])
        discovery_run = discovery.data["run_id"]
        self.service.execute(
            f"/approve {discovery_run} because reviewed discovery preparation",
            [],
            principal_id="telegram:123",
        )
        proposal = self.service.execute(
            f"/continue {discovery_run}",
            [],
            inputs={
                "discovery_evidence": {
                    "notes": "SAFE synthetic discovery notes retain unresolved questions.",
                    "sources": [
                        {
                            "source_id": "meeting-safe",
                            "source_type": "notes",
                            "location": "meeting:safe",
                        }
                    ],
                }
            },
        )

        self.assertEqual(proposal.data["workflow_id"], "discovery_evidence_to_growth_sprint_proposal")
        self.assertEqual(proposal.data["status"], "awaiting_approval")
        self.assertFalse(proposal.data["external_action_taken"])

    def test_additional_research_is_durable_idempotent_and_can_feed_a_new_blueprint(self) -> None:
        scope = hashlib.sha256(b"narratiive:safe-client").hexdigest()[:24]
        workspace = self.root / scope / "research" / "workspaces" / "narratiive"
        workspace.mkdir(parents=True)
        (workspace / "evidence.md").write_text(
            "SAFE approved evidence indicates that category language and buyer proof remain unresolved strategic choices.",
            encoding="utf-8",
        )
        research_inputs = {
            "approved_growth_sprint_scope": ["Category diagnosis", "Audience evidence", "Positioning choices"],
            "research_requirements": {
                "workstreams_and_questions": [
                    {"workstream": "category", "questions": ["How does the category describe the problem?"]}
                ]
            },
            "research_sources": [
                {
                    "source_id": "safe-approved-source",
                    "source_type": "document",
                    "uri": "evidence.md",
                    "policy": {"approved": True, "allow_local_files": True},
                }
            ],
            "client_context": {"name": "SAFE Executive Workflow Test"},
        }
        self.runtime.enqueue(
            "growth_sprint_to_research_engine",
            "safe-research-run",
            research_inputs,
            entity_id="safe-lead",
            correlation_id="safe-correlation",
        )
        self.runtime.advance("safe-research-run", lifecycle("safe-client"))
        request = {
            "focus": {
                "kind": "evidence_gap",
                "statement": "What direct evidence supports the strongest category entry point?",
            }
        }

        commissioned = self.service.execute(
            "/research safe-research-run because close the recorded category evidence gap",
            [],
            inputs=request,
        )
        replay = self.service.execute(
            "/research safe-research-run because close the recorded category evidence gap",
            [],
            inputs=request,
        )

        self.assertEqual(commissioned.data["status"], "complete")
        self.assertEqual(replay.data["run_id"], commissioned.data["run_id"])
        self.assertFalse(commissioned.data["external_action_taken"])
        iteration = self.runtime.runs.repository.load(commissioned.data["run_id"])
        self.assertEqual(iteration.input_payload["research_iteration"]["kind"], "evidence_gap")
        self.assertEqual(iteration.input_payload["research_iteration"]["source_run_id"], "safe-research-run")
        self.assertTrue(iteration.input_payload["_lineage"]["parent_artifact_ids"])
        self.assertTrue(iteration.stage("orchestrate_research").quality_result["passed"])

        restarted = TonyWorkflowCommandService(
            FallbackCommands(),
            FileWorkflowCommandBackend(self.root, dispatchers=self.dispatchers, environ={}),
        )
        status = restarted.execute(f"/workflow {commissioned.data['run_id']}", [])
        blueprint = restarted.execute(f"/continue {commissioned.data['run_id']}", [])
        self.assertEqual(status.data["status"], "complete")
        self.assertEqual(blueprint.data["workflow_id"], "research_to_growth_blueprint")
        self.assertEqual(blueprint.data["status"], "awaiting_approval")
        self.assertFalse(blueprint.data["external_action_taken"])

    def test_additional_research_rejects_unapproved_sources_without_creating_a_run(self) -> None:
        before = {state.run_id for state in self.service.backend.list_states()}

        result = self.service.execute(
            "/research safe-executive-run because test an unsupported hypothesis",
            [],
            inputs={
                "focus": {"kind": "hypothesis", "statement": "Buyers prefer a narrowly framed category promise."},
                "research_sources": [
                    {
                        "source_id": "unsafe-source",
                        "source_type": "web",
                        "uri": "https://example.invalid",
                        "policy": {"approved": False},
                    }
                ],
            },
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(before, {state.run_id for state in self.service.backend.list_states()})

    def test_malformed_persisted_state_fails_closed(self) -> None:
        broken = self.root / "invalid-scope" / "runs"
        broken.mkdir(parents=True)
        (broken / "broken.json").write_text("{not-json", encoding="utf-8")

        response = self.service.execute("/work", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "workflow_state_unavailable")


if __name__ == "__main__":
    unittest.main()
