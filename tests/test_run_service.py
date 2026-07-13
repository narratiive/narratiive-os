import tempfile
import unittest
from pathlib import Path

from runtime.definitions import load_workflow_definition, workflow_definition_from_dict
from runtime.models import ArtifactRef, StageStatus, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.run_service import WorkflowRunService


class WorkflowDefinitionTests(unittest.TestCase):
    def test_loads_growth_blueprint_pipeline(self) -> None:
        definition = load_workflow_definition("workflows/growth_blueprint_pipeline.json")
        self.assertEqual(definition.workflow_id, "growth_blueprint_pipeline")
        self.assertEqual(len(definition.stages), 5)
        self.assertEqual(definition.stages[0].stage_id, "research_analyst")
        self.assertEqual(definition.stages[-1].stage_id, "quality_reviewer")

    def test_rejects_duplicate_stages(self) -> None:
        with self.assertRaises(ValueError):
            workflow_definition_from_dict(
                {
                    "workflow_id": "duplicate",
                    "stages": [
                        {"stage_id": "research", "agent_ref": "agents/research.md"},
                        {"stage_id": "research", "agent_ref": "agents/research.md"},
                    ],
                }
            )


class WorkflowRunServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = FileWorkflowRunRepository(root / "runs")
        self.event_log = JsonlEventLog(root / "events")
        self.service = WorkflowRunService(self.repository, self.event_log)
        self.definition = load_workflow_definition("workflows/growth_blueprint_pipeline.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_run_persists_initial_state_and_event(self) -> None:
        state = self.service.create_run(
            self.definition,
            "run-001",
            {"client_inputs", "source_material"},
        )

        restored = self.repository.load("run-001")
        events = self.event_log.read("run-001")

        self.assertEqual(state.current_stage_id, "research_analyst")
        self.assertEqual(restored.stage("research_analyst").status, StageStatus.READY)
        self.assertEqual([event.event_type for event in events], ["workflow.created"])

    def test_stage_completion_advances_and_records_audit_event(self) -> None:
        self.service.create_run(
            self.definition,
            "run-001",
            {"client_inputs", "source_material"},
        )
        self.service.start_stage("run-001", "research_analyst")
        state = self.service.complete_stage(
            "run-001",
            "research_analyst",
            [
                ArtifactRef(
                    "research-001",
                    "completed_research_inputs",
                    "runs/run-001/research.md",
                )
            ],
            {"completed_research_inputs"},
        )

        self.assertEqual(state.current_stage_id, "strategy_director")
        self.assertEqual(state.stage("strategy_director").status, StageStatus.READY)
        self.assertEqual(
            [event.event_type for event in self.event_log.read("run-001")],
            ["workflow.created", "stage.started", "stage.completed"],
        )

    def test_duplicate_run_is_rejected(self) -> None:
        self.service.create_run(
            self.definition,
            "run-001",
            {"client_inputs", "source_material"},
        )
        with self.assertRaises(ValueError):
            self.service.create_run(
                self.definition,
                "run-001",
                {"client_inputs", "source_material"},
            )

    def test_blocked_run_can_resume_after_inputs_arrive(self) -> None:
        state = self.service.create_run(self.definition, "run-001", {"client_inputs"})
        self.assertEqual(state.status, WorkflowStatus.BLOCKED)

        state = self.service.resume_stage(
            "run-001",
            "research_analyst",
            {"client_inputs", "source_material"},
        )

        self.assertEqual(state.status, WorkflowStatus.ACTIVE)
        self.assertEqual(state.stage("research_analyst").status, StageStatus.READY)
        self.assertEqual(
            [event.event_type for event in self.event_log.read("run-001")],
            ["workflow.created", "stage.resumed"],
        )


if __name__ == "__main__":
    unittest.main()
