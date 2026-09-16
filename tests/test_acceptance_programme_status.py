from __future__ import annotations

import unittest

from runtime.acceptance_programme_status import AcceptanceProgrammeStatusBuilder
from runtime.models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus
from runtime.workflow_registry import build_narratiive_workflow_registry


def completed_state(
    workflow_id: str,
    run_id: str,
    *,
    client_id: str = "safe-katkin",
    input_payload=None,
) -> WorkflowState:
    stage = StageRecord(
        stage_id="safe-stage",
        agent_ref="capability:safe",
        status=StageStatus.COMPLETED,
        quality_result={"passed": True},
        output_artifacts=[
            ArtifactRef(
                artifact_id=f"artifact-{run_id}",
                artifact_type="workflow_step_output",
                location=f"/safe/{run_id}.json",
                checksum=f"checksum-{run_id}",
            )
        ],
    )
    return WorkflowState(
        workflow_id=workflow_id,
        run_id=run_id,
        stages=[stage],
        status=WorkflowStatus.COMPLETE,
        workspace_id="narratiive",
        client_id=client_id,
        entity_id=client_id,
        input_payload=dict(input_payload or {}),
    )


class AcceptanceProgrammeStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = AcceptanceProgrammeStatusBuilder(build_narratiive_workflow_registry())

    def test_projects_research_checkpoint_and_product_canon_conflict(self) -> None:
        blueprint = completed_state("growth_diagnostic_to_blueprint_lite", "safe-blueprint")
        blueprint.approval_status = "approved"
        proposal = completed_state(
            "discovery_evidence_to_growth_sprint_proposal",
            "safe-proposal",
            input_payload={
                "discovery_evidence": {"notes": "SAFE evidence"},
                "_promised_work": {"commitment_id": "safe"},
            },
        )
        proposal.approval_status = "approved"
        proposal.approval_history = [
            {
                "approver": "telegram:safe",
                "approval_binding": {"artifact_id": "artifact-safe-proposal"},
            }
        ]
        proposal.external_action_receipts = [
            {
                "receipt": {
                    "kind": "internal_artifact_review_delivery",
                    "message_id": "gmail-safe",
                }
            }
        ]
        proposal.promised_work_delivery = {"status": "delivered"}
        research = completed_state("growth_sprint_to_research_engine", "safe-research")
        research.input_payload["_promised_work"] = {"commitment_id": "safe-research"}
        research.promised_work_delivery = {"status": "delivered"}

        status = self.builder.build(
            (blueprint, proposal, research),
            scenario_client_id="safe-katkin",
            deployment={"deployed_revision": "safe-revision", "status": "healthy"},
            service_health=({"name": "runtime", "healthy": True},),
            conversation_work=(
                {
                    "work_id": "safe-conversation",
                    "state": "completed",
                    "external_action_taken": True,
                },
            ),
        )

        self.assertEqual(status["deployed_revision"], "safe-revision")
        self.assertEqual(status["last_verified_checkpoint"]["capability"], "Research")
        self.assertEqual(status["current_stage"], "Strategy Thesis product-canon gate")
        self.assertEqual(status["next_unimplemented_capability"], "Strategic synthesis")
        self.assertEqual(status["architectural_conflicts"][0]["observed"], "research_to_growth_blueprint")
        self.assertTrue(status["requires_matt"])
        capabilities = {item["capability"]: item for item in status["capabilities"]}
        self.assertEqual(capabilities["Research"]["status"], "LIVE_PROVEN")
        self.assertEqual(capabilities["Discovery"]["status"], "LIVE_PROVEN")
        self.assertEqual(capabilities["Strategy Thesis"]["status"], "NOT_IMPLEMENTED")
        self.assertEqual(capabilities["Human review delivery"]["status"], "LIVE_PROVEN")
        self.assertEqual(capabilities["Conversational approval"]["status"], "LIVE_PROVEN")

    def test_projection_does_not_infer_live_recovery_from_service_health(self) -> None:
        status = self.builder.build(
            (completed_state("growth_diagnostic_to_blueprint_lite", "safe-blueprint"),),
            scenario_client_id="safe-katkin",
            deployment={"deployed_revision": "safe-revision", "status": "healthy"},
            service_health=({"name": "runtime", "healthy": True},),
        )

        capabilities = {item["capability"]: item for item in status["capabilities"]}
        self.assertEqual(capabilities["Runtime services"]["status"], "LIVE_PROVEN")
        self.assertEqual(capabilities["Restart/recovery"]["status"], "IMPLEMENTED")
        self.assertIn("No standalone live recovery receipt", capabilities["Restart/recovery"]["note"])

    def test_missing_scenario_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "no persisted workflow runs"):
            self.builder.build(
                (),
                scenario_client_id="missing",
                deployment={},
            )


if __name__ == "__main__":
    unittest.main()
