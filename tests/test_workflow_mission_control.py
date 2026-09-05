from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.models import WorkflowStatus
from runtime.tony_workflow_commands import FileWorkflowCommandBackend
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from runtime.workflow_mission_control import WorkflowMissionControlProjector


def _blueprint_output() -> dict:
    return {
        "blueprint_lite": "A substantive SAFE synthetic Blueprint Lite with a clear strategic point of view.",
        "diagnostic_signals_used": ["overall score", "main blockage"],
        "diagnostic_input_coverage": {"complete": True},
        "source_backed_evidence": [
            {"source": "https://example.invalid", "fact": "Synthetic evidence"}
        ],
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


class WorkflowMissionControlTests(unittest.TestCase):
    def test_projects_approval_artefact_next_action_and_external_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = build_tony_workflow_runtime(
                Path(temporary),
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={"Claude": lambda _: _blueprint_output()},
                environ={},
            )
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-mission-run",
                {
                    "diagnostic_input_package": {"overall_score": 42},
                    "company": "SAFE Mission Control Company",
                },
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            runtime.advance(
                "safe-mission-run",
                ClientLifecycleRecord(
                    client_id="safe-client",
                    client_name="SAFE Mission Control Company",
                    stage=ClientLifecycleStage.BLUEPRINT_LITE,
                    owner="Tony",
                    next_action="Prepare internal work",
                    evidence=("synthetic:test",),
                ),
            )
            state = runtime.runs.load_run("safe-mission-run")

            view = WorkflowMissionControlProjector(
                workspace_id="narratiive"
            ).project((state,))

            summary = view.runs[0]
            self.assertEqual(summary["status"], "awaiting_approval")
            self.assertTrue(summary["approval_required"])
            self.assertTrue(summary["quality_passed"])
            self.assertIsNotNone(summary["latest_artefact"])
            self.assertNotIn("location", summary["latest_artefact"])
            self.assertTrue(summary["proposed_next_action"])
            self.assertFalse(summary["external_action_taken"])
            self.assertEqual(view.workstreams[0].state, "tested")
            self.assertEqual(len(view.approvals_required), 1)

    def test_cross_workspace_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = build_tony_workflow_runtime(
                temporary,
                workspace_id="another-workspace",
                client_id="safe-client",
                dispatchers={},
                environ={},
            )
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "cross-workspace-run",
                {"diagnostic_input_package": {"overall_score": 42}},
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )

            with self.assertRaisesRegex(ValueError, "workspace mismatch"):
                WorkflowMissionControlProjector(
                    workspace_id="narratiive"
                ).project((runtime.runs.load_run("cross-workspace-run"),))

    def test_blocker_is_reported_without_claiming_external_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = build_tony_workflow_runtime(
                temporary,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={},
                environ={},
            )
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-blocked-run",
                {"diagnostic_input_package": {"overall_score": 42}},
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            state = runtime.runs.load_run("safe-blocked-run")
            state.status = WorkflowStatus.BLOCKED
            state.blocker = "worker_unavailable:strategic_reasoning"
            runtime.runs.repository.save(state)

            view = WorkflowMissionControlProjector(
                workspace_id="narratiive"
            ).project((state,))

            self.assertEqual(view.runs[0]["status"], "blocked")
            self.assertEqual(view.workstreams[0].state, "blocked")
            self.assertEqual(
                view.workstreams[0].blocker,
                "worker_unavailable:strategic_reasoning",
            )
            self.assertFalse(view.runs[0]["external_action_taken"])

    def test_scoped_backend_hides_other_workspace_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for workspace, client, run_id in (
                ("narratiive", "safe-client", "visible-run"),
                ("other-workspace", "other-client", "hidden-run"),
            ):
                runtime = build_tony_workflow_runtime(
                    temporary,
                    workspace_id=workspace,
                    client_id=client,
                    dispatchers={},
                    environ={},
                )
                runtime.enqueue(
                    "growth_diagnostic_to_blueprint_lite",
                    run_id,
                    {"diagnostic_input_package": {"overall_score": 42}},
                    entity_id=f"{run_id}-lead",
                    correlation_id=f"{run_id}-correlation",
                )

            states = FileWorkflowCommandBackend(
                temporary,
                workspace_id="narratiive",
            ).list_states()

            self.assertEqual([state.run_id for state in states], ["visible-run"])


if __name__ == "__main__":
    unittest.main()
