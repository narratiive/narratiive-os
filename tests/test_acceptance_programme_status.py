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
        self.assertIn("No valid live recovery receipt", capabilities["Restart/recovery"]["note"])

    def test_matching_recovery_receipt_proves_live_restart_recovery(self) -> None:
        status = self.builder.build(
            (completed_state("growth_diagnostic_to_blueprint_lite", "safe-blueprint"),),
            scenario_client_id="safe-katkin",
            deployment={"deployed_revision": "safe-revision", "status": "healthy"},
            service_health=(
                {"name": "runtime-gateway", "healthy": True},
                {"name": "tony-http-bridge", "healthy": True},
            ),
            recovery={
                "status": "recovered",
                "restarted_services": ["com.narratiive.tony-http-bridge"],
                "failed_services": ["tony-http-bridge"],
                "deployment_healthy": True,
                "exit_code_before": 20,
                "exit_code_after": 0,
                "attempted_at": "2026-09-16T07:00:00Z",
                "deployed_revision": "safe-revision",
            },
        )

        capability = next(item for item in status["capabilities"] if item["capability"] == "Restart/recovery")
        self.assertEqual(capability["status"], "LIVE_PROVEN")
        self.assertIn("restarted:com.narratiive.tony-http-bridge", capability["evidence"])

    def test_stale_or_healthy_only_recovery_receipt_does_not_prove_recovery(self) -> None:
        for recovery in (
            {"status": "healthy", "deployed_revision": "safe-revision"},
            {
                "status": "recovered",
                "restarted_services": ["com.narratiive.tony-http-bridge"],
                "failed_services": ["tony-http-bridge"],
                "deployment_healthy": True,
                "exit_code_before": 20,
                "exit_code_after": 0,
                "attempted_at": "2026-09-16T07:00:00Z",
                "deployed_revision": "stale-revision",
            },
        ):
            with self.subTest(recovery=recovery):
                status = self.builder.build(
                    (completed_state("growth_diagnostic_to_blueprint_lite", "safe-blueprint"),),
                    scenario_client_id="safe-katkin",
                    deployment={"deployed_revision": "safe-revision", "status": "healthy"},
                    service_health=({"name": "runtime-gateway", "healthy": True},),
                    recovery=recovery,
                )
                capability = next(item for item in status["capabilities"] if item["capability"] == "Restart/recovery")
                self.assertEqual(capability["status"], "IMPLEMENTED")

    def test_matching_attention_receipt_proves_live_suppression(self) -> None:
        status = self.builder.build(
            (completed_state("growth_diagnostic_to_blueprint_lite", "safe-blueprint"),),
            scenario_client_id="safe-katkin",
            deployment={"deployed_revision": "safe-revision", "status": "deployed"},
            attention={
                "status": "accepted",
                "checked_at": "2026-09-16T08:00:00+00:00",
                "deployed_revision": "safe-revision",
                "raw_lead_count": 3,
                "visible_lead_count": 1,
                "hidden_lead_count": 2,
                "visible_lead_ids": ["visible"],
                "hidden_lead_ids": ["hidden-a", "hidden-b"],
                "morning_command_status": "healthy",
                "lead_command_status": "healthy",
                "duplicate_status": "duplicate_suppressed",
                "duplicate_attempts": 0,
                "external_action_taken": False,
                "client_workflow_mutations": 0,
            },
        )

        capability = next(item for item in status["capabilities"] if item["capability"] == "Attention suppression")
        self.assertEqual(capability["status"], "LIVE_PROVEN")
        self.assertIn("hidden_records:2", capability["evidence"])

    def test_stale_or_unsafe_attention_receipt_does_not_prove_suppression(self) -> None:
        base = {
            "status": "accepted",
            "deployed_revision": "safe-revision",
            "raw_lead_count": 2,
            "visible_lead_count": 1,
            "hidden_lead_count": 1,
            "visible_lead_ids": ["visible"],
            "hidden_lead_ids": ["hidden"],
            "morning_command_status": "healthy",
            "lead_command_status": "healthy",
            "duplicate_status": "duplicate_suppressed",
            "duplicate_attempts": 0,
            "external_action_taken": False,
            "client_workflow_mutations": 0,
        }
        for change in (
            {"deployed_revision": "stale"},
            {"duplicate_attempts": 1},
            {"external_action_taken": True},
            {"hidden_lead_ids": []},
            {"hidden_lead_ids": [{"invalid": "shape"}]},
            {"raw_lead_count": "2"},
            {"visible_lead_count": 0},
        ):
            with self.subTest(change=change):
                receipt = {**base, **change}
                status = self.builder.build(
                    (completed_state("growth_diagnostic_to_blueprint_lite", "safe-blueprint"),),
                    scenario_client_id="safe-katkin",
                    deployment={"deployed_revision": "safe-revision", "status": "deployed"},
                    attention=receipt,
                )
                capability = next(item for item in status["capabilities"] if item["capability"] == "Attention suppression")
                self.assertEqual(capability["status"], "IMPLEMENTED")

    def test_missing_scenario_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "no persisted workflow runs"):
            self.builder.build(
                (),
                scenario_client_id="missing",
                deployment={},
            )


if __name__ == "__main__":
    unittest.main()
