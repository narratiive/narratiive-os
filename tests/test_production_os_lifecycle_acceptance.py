from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_tony_workflow_runtime import _blueprint_output
from tests.test_workflow_quality import discovery_output, growth_blueprint_output, proposal_output


class Fallback:
    def execute(self, command, objects):
        return CommandResponse("fallback", "healthy", "fallback", {})


def lifecycle() -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id="safe-final-client",
        client_name="SAFE PRODUCTION OS FINAL E2E TEST ONLY",
        stage=ClientLifecycleStage.BLUEPRINT_LITE,
        owner="Tony",
        next_action="Prepare the next internal workflow artefact.",
        evidence=("synthetic:safe-final-e2e",),
        acquisition_path=AcquisitionPath.INBOUND,
    )


class ProductionOSLifecycleAcceptanceTests(unittest.TestCase):
    def test_safe_company_traverses_internal_chain_with_quality_lineage_and_gates(self) -> None:
        calls = []

        def claude(contract):
            calls.append(contract)
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if workflow_id == "blueprint_lite_to_discovery_preparation":
                return discovery_output()
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                return proposal_output()
            if workflow_id == "research_to_growth_blueprint":
                return growth_blueprint_output()
            return _blueprint_output()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dispatchers = {"Claude": claude}
            runtime = build_tony_workflow_runtime(
                root,
                workspace_id="agency",
                client_id="safe-final-client",
                dispatchers=dispatchers,
                environ={},
            )
            research_workspace = runtime.coordinator.artifacts.root.parent / "research" / "workspaces" / "agency"
            research_workspace.mkdir(parents=True)
            (research_workspace / "category.md").write_text(
                "SAFE synthetic category evidence says broad category language makes the offer difficult to distinguish and leaves strategic choice unresolved.",
                encoding="utf-8",
            )
            (research_workspace / "audience.md").write_text(
                "SAFE synthetic audience evidence records that urgent buyers ask for proof and clearer outcomes before they commit to further discussion.",
                encoding="utf-8",
            )
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-final-os-run",
                {
                    "diagnostic_input_package": {
                        "overall_score": 42,
                        "main_blockage": "The offer is difficult to distinguish.",
                        "raw_answers": {"challenge": "SAFE synthetic evidence only"},
                    },
                    "company": "SAFE PRODUCTION OS FINAL E2E TEST ONLY",
                    "email": "safe-final-production-os@acceptance.invalid",
                },
                entity_id="safe-final-lead",
                correlation_id="safe-final-correlation",
            )
            runtime.advance("safe-final-os-run", lifecycle())

            def commands() -> TonyWorkflowCommandService:
                return TonyWorkflowCommandService(
                    Fallback(),
                    FileWorkflowCommandBackend(root, dispatchers=dispatchers, environ={}),
                )

            service = commands()
            initial = service.execute("/workflow SAFE PRODUCTION OS FINAL E2E TEST ONLY", [])
            self.assertEqual(initial.data["status"], "awaiting_approval")
            self.assertTrue(initial.data["quality_passed"])

            service.execute(
                "/approve safe-final-os-run because SAFE Blueprint Lite reviewed",
                [],
                principal_id="openclaw:native-approval",
            )
            discovery = service.execute("/continue safe-final-os-run", [])
            discovery_run = discovery.data["run_id"]
            self.assertEqual(discovery.data["workflow_id"], "blueprint_lite_to_discovery_preparation")
            self.assertEqual(discovery.data["status"], "awaiting_approval")

            rejected = service.execute(
                f"/reject {discovery_run} because add a stronger uncertainty statement",
                [],
                principal_id="openclaw:native-approval",
            )
            self.assertEqual(rejected.data["status"], "active")
            revised = service.execute(f"/continue {discovery_run}", [])
            self.assertEqual(revised.data["status"], "awaiting_approval")
            service.execute(
                f"/approve {discovery_run} because revised internal discovery preparation reviewed",
                [],
                principal_id="openclaw:native-approval",
            )

            proposal = service.execute(
                f"/continue {discovery_run}",
                [],
                inputs={
                    "discovery_evidence": {
                        "notes": "SAFE synthetic discovery: differentiation remains unresolved; direct customer validation is still required.",
                        "sources": [
                            {
                                "source_id": "safe-discovery-notes",
                                "source_type": "notes",
                                "location": "meeting:safe-final",
                            }
                        ],
                    }
                },
            )
            proposal_run = proposal.data["run_id"]
            self.assertEqual(proposal.data["workflow_id"], "discovery_evidence_to_growth_sprint_proposal")
            self.assertEqual(proposal.data["status"], "awaiting_approval")
            service.execute(
                f"/approve {proposal_run} because SAFE Growth Sprint scope reviewed",
                [],
                principal_id="openclaw:native-approval",
            )

            research = service.execute(
                f"/continue {proposal_run}",
                [],
                inputs={
                    "research_sources": [
                        {
                            "source_id": "safe-category",
                            "source_type": "document",
                            "uri": "category.md",
                            "policy": {"approved": True, "allow_local_files": True},
                        },
                        {
                            "source_id": "safe-audience",
                            "source_type": "document",
                            "uri": "audience.md",
                            "policy": {"approved": True, "allow_local_files": True},
                        },
                    ]
                },
            )
            research_run = research.data["run_id"]
            self.assertEqual(research.data["workflow_id"], "growth_sprint_to_research_engine")
            self.assertEqual(research.data["status"], "complete")
            research_backend = commands().backend
            research_state = next(item for item in research_backend.list_states() if item.run_id == research_run)
            research_output = research_backend.latest_output(research_state)
            self.assertIsNotNone(research_output)
            self.assertTrue(research_output["source_provenance"])
            self.assertTrue(research_output["fact_interpretation_hypothesis_lineage"]["facts"])

            blueprint = service.execute(f"/continue {research_run}", [])
            blueprint_run = blueprint.data["run_id"]
            self.assertEqual(blueprint.data["workflow_id"], "research_to_growth_blueprint")
            self.assertEqual(blueprint.data["status"], "awaiting_approval")
            self.assertTrue(blueprint.data["quality_passed"])
            self.assertFalse(blueprint.data["external_action_taken"])

            restarted = commands()
            recovered = restarted.execute("/recover", [])
            still_waiting = restarted.execute(f"/workflow {blueprint_run}", [])
            self.assertEqual(recovered.status, "healthy")
            self.assertEqual(still_waiting.data["status"], "awaiting_approval")
            self.assertFalse(still_waiting.data["external_action_taken"])
            approvals = restarted.execute("/approvals", [])
            self.assertIn(blueprint_run, {item["run_id"] for item in approvals.data["runs"]})

            approved = restarted.execute(
                f"/approve {blueprint_run} because SAFE internal Growth Blueprint draft reviewed",
                [],
                principal_id="openclaw:native-approval",
            )
            self.assertEqual(approved.data["status"], "complete")
            self.assertFalse(approved.data["external_action_taken"])
            self.assertGreaterEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main()
