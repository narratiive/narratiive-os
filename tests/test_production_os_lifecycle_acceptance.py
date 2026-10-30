from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleRecord, ClientLifecycleStage
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
        blueprint_attempts = 0

        def claude(contract):
            nonlocal blueprint_attempts
            calls.append(contract)
            target = contract.get("target", {})
            workflow_context = target.get("workflow_context", {})
            workflow_id = workflow_context.get("workflow_id")
            if workflow_id == "blueprint_lite_to_discovery_preparation":
                return discovery_output()
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                return proposal_output()
            if workflow_id == "research_to_strategic_synthesis":
                return strategic_synthesis_output()
            if workflow_id == "strategic_synthesis_to_strategy_thesis":
                return strategy_thesis_output()
            if workflow_id == "strategy_thesis_to_growth_blueprint":
                if workflow_context.get("stage_id") == "direct_growth_blueprint":
                    client = target.get("client_context", {})
                    return blueprint_director_output(
                        client_name=str(client.get("name") or client.get("company") or "SAFE PRODUCTION OS FINAL E2E TEST ONLY")
                    )
                blueprint_attempts += 1
                candidate = growth_blueprint_output()
                if blueprint_attempts == 1:
                    candidate["central_thesis"] = {
                        "insight": "Generic awareness opportunity",
                        "why_non_obvious": "Not yet demonstrated",
                        "competitor_substitution_test": "Any competitor could use this",
                        "commercial_consequence": "Do more marketing activity",
                        "evidence_refs": [],
                    }
                return candidate
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
                inputs={"approval_token": initial.data["approval_token"]},
            )
            discovery = service.execute("/continue safe-final-os-run", [])
            discovery_run = discovery.data["run_id"]
            self.assertEqual(discovery.data["workflow_id"], "blueprint_lite_to_discovery_preparation")
            self.assertEqual(discovery.data["status"], "awaiting_approval")

            rejected = service.execute(
                f"/reject {discovery_run} because add a stronger uncertainty statement",
                [],
                principal_id="openclaw:native-approval",
                inputs={"approval_token": discovery.data["approval_token"]},
            )
            self.assertEqual(rejected.data["status"], "active")
            revised = service.execute(f"/continue {discovery_run}", [])
            self.assertEqual(revised.data["status"], "awaiting_approval")
            service.execute(
                f"/approve {discovery_run} because revised internal discovery preparation reviewed",
                [],
                principal_id="openclaw:native-approval",
                inputs={"approval_token": revised.data["approval_token"]},
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
            proposal_state = next(item for item in commands().backend.list_states() if item.run_id == proposal_run)
            artifact = proposal_state.stages[-1].output_artifacts[-1]
            offer = {
                "proposal_id": "safe-final-fieldwork-v1", "recipient_email": "client@example.invalid",
                "proposal_url": "https://drive.example.invalid/safe-final-fieldwork-v1",
                "proposal_artifact_id": artifact.artifact_id, "proposal_artifact_version": "v1",
                "proposal_artifact_checksum": artifact.checksum, "fixed_investment_minor": 600000,
                "deposit_amount_minor": 300000, "currency": "GBP",
                "scope_summary": "Synthetic FIELDWORK scope for lifecycle acceptance coverage.",
                "balance_terms": "Synthetic balance due on delivery.",
                "service_terms_url": "https://narratiive.example.invalid/terms",
            }
            offer_preview = service.execute(
                f"/fieldwork-offer {proposal_run}", [],
                inputs={"approval_token": proposal.data["approval_token"], "fieldwork_commercial_offer": offer},
            )
            service.execute(
                f"/approve {proposal_run} because SAFE Growth Sprint scope reviewed",
                [],
                principal_id="openclaw:native-approval",
                inputs={
                    "approval_token": proposal.data["approval_token"],
                    "fieldwork_commercial_offer": offer,
                    "commercial_offer_digest": offer_preview.data["commercial_offer_digest"],
                },
            )

            blocked = service.execute(f"/continue {proposal_run}", [])
            self.assertEqual(blocked.status, "error")
            self.assertIn("verified payment authorisation", blocked.message)
            states = commands().backend.list_states()
            self.assertFalse(any(item.workflow_id == "growth_sprint_to_research_engine" for item in states))


if __name__ == "__main__":
    unittest.main()
