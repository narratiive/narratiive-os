from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.research_workflow_adapter import ResearchWorkflowAdapter
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_workflow_quality import growth_blueprint_output


def lifecycle() -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id="safe-research-client",
        client_name="SAFE Research Production Test",
        stage=ClientLifecycleStage.RESEARCH,
        owner="Tony",
        next_action="Conduct approved internal research",
        evidence=("synthetic:test",),
    )


class ResearchWorkflowAdapterTests(unittest.TestCase):
    def test_missing_workspace_identity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = ResearchWorkflowAdapter(tmp)
            with self.assertRaisesRegex(ValueError, "workspace identity"):
                adapter({
                    "workflow_context": {
                        "workflow_id": "growth_sprint_to_research_engine",
                        "run_id": "unsafe-unscoped-run",
                    },
                    "research_requirements": {
                        "workstreams_and_questions": [{"questions": ["What is known?"]}],
                    },
                    "research_sources": [],
                })

    def test_bounded_research_runs_with_provenance_then_prepares_blueprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-research-client",
                dispatchers={"Claude": lambda contract: growth_blueprint_output()},
                environ={},
            )
            workspace = runtime.coordinator.artifacts.root.parent / "research" / "workspaces" / "agency"
            workspace.mkdir(parents=True)
            (workspace / "source-one.md").write_text(
                "SAFE synthetic source: prospects value strategic clarity but cannot distinguish the current offer from broad alternatives.",
                encoding="utf-8",
            )
            (workspace / "source-two.md").write_text(
                "SAFE synthetic source: qualified buyers ask for proof earlier and the team lacks direct customer language.",
                encoding="utf-8",
            )
            runtime.enqueue(
                "growth_sprint_to_research_engine",
                "safe-research-run",
                {
                    "approved_growth_sprint_scope": ["Audience", "Category", "Positioning"],
                    "research_requirements": {
                        "workstreams_and_questions": [
                            {"workstream": "Audience", "questions": ["Which audience situation creates the strongest urgency?"]},
                            {"workstream": "Category", "questions": ["Which conventions make the offer appear interchangeable?"]},
                        ],
                        "known_gaps": ["Direct customer interviews remain unavailable"],
                    },
                    "research_sources": [
                        {"source_id": "source-1", "source_type": "document", "uri": "source-one.md", "policy": {"approved": True, "allow_local_files": True}},
                        {"source_id": "source-2", "source_type": "document", "uri": "source-two.md", "policy": {"approved": True, "allow_local_files": True}},
                    ],
                    "client_context": {"name": "SAFE Research Production Test", "workspace_id": "agency"},
                },
                entity_id="safe-research-client",
                correlation_id="safe-research-correlation",
            )

            research = runtime.advance("safe-research-run", lifecycle())
            research_state = runtime.status("safe-research-run")

            self.assertEqual(research.status, "complete", research_state)
            self.assertTrue(research_state["stages"][0]["quality_result"]["passed"])
            self.assertEqual(research_state["stages"][0]["side_effect_classification"], "external_read")
            self.assertFalse(research_state["external_action_taken"])
            output_path = Path(research_state["stages"][0]["output_artifacts"][0]["location"])
            self.assertTrue(output_path.exists())

            blueprint = runtime.handoff("safe-research-run", lifecycle())
            blueprint_state = runtime.status(blueprint.run_id)

            self.assertEqual(blueprint.workflow_id, "research_to_growth_blueprint")
            self.assertEqual(blueprint.status, "awaiting_approval")
            self.assertTrue(blueprint_state["stages"][0]["quality_result"]["passed"])
            self.assertEqual(blueprint_state["approval_status"], "pending")
            self.assertFalse(blueprint_state["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
