import unittest

from runtime.models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus
from runtime.state_machine import InvalidTransition, WorkflowEngine


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WorkflowEngine()
        self.state = WorkflowState(
            workflow_id="growth_blueprint_pipeline",
            run_id="run-001",
            stages=[
                StageRecord(
                    stage_id="research_analyst",
                    agent_ref="agents/research_analyst.md",
                    required_inputs=("client_inputs", "source_material"),
                ),
                StageRecord(
                    stage_id="strategy_director",
                    agent_ref="agents/strategy_director.md",
                    required_inputs=("completed_research_inputs",),
                ),
            ],
        )

    def test_initialise_marks_first_stage_ready(self) -> None:
        self.engine.initialise(self.state, {"client_inputs", "source_material"})
        self.assertEqual(self.state.current_stage_id, "research_analyst")
        self.assertEqual(self.state.stage("research_analyst").status, StageStatus.READY)
        self.assertEqual(self.state.status, WorkflowStatus.ACTIVE)

    def test_initialise_blocks_when_input_is_missing(self) -> None:
        self.engine.initialise(self.state, {"client_inputs"})
        stage = self.state.stage("research_analyst")
        self.assertEqual(stage.status, StageStatus.BLOCKED)
        self.assertEqual(stage.missing_inputs, ["source_material"])
        self.assertEqual(self.state.status, WorkflowStatus.BLOCKED)

    def test_completion_advances_to_next_stage(self) -> None:
        self.engine.initialise(self.state, {"client_inputs", "source_material"})
        self.engine.start_stage(self.state, "research_analyst")
        artifact = ArtifactRef(
            artifact_id="research-001",
            artifact_type="completed_research_inputs",
            location="runs/run-001/research.md",
        )
        self.engine.complete_stage(
            self.state,
            "research_analyst",
            [artifact],
            next_available_inputs={"completed_research_inputs"},
        )
        self.assertEqual(self.state.stage("research_analyst").status, StageStatus.COMPLETED)
        self.assertEqual(self.state.stage("strategy_director").status, StageStatus.READY)
        self.assertEqual(self.state.current_stage_id, "strategy_director")

    def test_last_stage_completion_finishes_workflow(self) -> None:
        self.engine.initialise(self.state, {"client_inputs", "source_material"})
        self.engine.start_stage(self.state, "research_analyst")
        research = ArtifactRef("research-001", "completed_research_inputs", "runs/run-001/research.md")
        self.engine.complete_stage(
            self.state,
            "research_analyst",
            [research],
            {"completed_research_inputs"},
        )
        self.engine.start_stage(self.state, "strategy_director")
        blueprint = ArtifactRef("blueprint-001", "growth_blueprint", "runs/run-001/blueprint.md")
        self.engine.complete_stage(self.state, "strategy_director", [blueprint])
        self.assertEqual(self.state.status, WorkflowStatus.COMPLETE)
        self.assertIsNone(self.state.current_stage_id)

    def test_cannot_complete_without_output_artifact(self) -> None:
        self.engine.initialise(self.state, {"client_inputs", "source_material"})
        self.engine.start_stage(self.state, "research_analyst")
        with self.assertRaises(InvalidTransition):
            self.engine.complete_stage(self.state, "research_analyst", [])

    def test_cannot_skip_current_stage(self) -> None:
        self.engine.initialise(self.state, {"client_inputs", "source_material"})
        with self.assertRaises(InvalidTransition):
            self.engine.start_stage(self.state, "strategy_director")

    def test_retry_increments_counter_and_can_resume(self) -> None:
        self.engine.initialise(self.state, {"client_inputs", "source_material"})
        self.engine.start_stage(self.state, "research_analyst")
        self.engine.request_retry(self.state, "research_analyst", "temporary model timeout")
        stage = self.state.stage("research_analyst")
        self.assertEqual(stage.retry_count, 1)
        self.assertEqual(stage.status, StageStatus.RETRY_REQUIRED)
        self.engine.resume_stage(self.state, "research_analyst", {"client_inputs", "source_material"})
        self.assertEqual(stage.status, StageStatus.READY)


if __name__ == "__main__":
    unittest.main()
