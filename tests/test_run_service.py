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

    def test_loads_declarative_step_contracts_without_requiring_a_fixed_worker(self) -> None:
        definition = workflow_definition_from_dict(
            {
                "workflow_id": "generic_prepare",
                "entity_type": "lead",
                "next_workflow_id": "next_prepare",
                "failure_policy": "block_and_escalate",
                "stages": [
                    {
                        "stage_id": "prepare",
                        "agent_ref": "",
                        "capability": "strategic_reasoning",
                        "required_inputs": ["diagnostic"],
                        "input_contract": {"required_fields": ["diagnostic"]},
                        "output_contract": {"required_fields": ["artefact", "recommendation"]},
                        "quality_contract": "strict_quality_gate",
                        "retry_policy": {"max_attempts": 2},
                        "approval_policy": {"required": True, "before_external_action": True},
                        "side_effect_classification": "preparation",
                    }
                ],
            }
        )
        step = definition.stages[0]
        self.assertEqual(step.capability, "strategic_reasoning")
        self.assertEqual(step.output_contract.required_fields, ("artefact", "recommendation"))
        self.assertEqual(step.retry_policy.max_attempts, 2)
        self.assertTrue(step.approval_policy.required)
        self.assertEqual(definition.new_state("run-1").stages[0].agent_ref, "capability:strategic_reasoning")


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

    def test_identity_input_attempt_and_quality_state_survive_restart(self) -> None:
        definition = workflow_definition_from_dict(
            {
                "workflow_id": "durable_prepare",
                "approval_required": True,
                "stages": [
                    {
                        "stage_id": "prepare",
                        "agent_ref": "worker-a",
                        "required_inputs": ["brief"],
                        "retry_policy": {"max_attempts": 2},
                        "quality_contract": "quality-a",
                    }
                ],
            }
        )
        created = self.service.create_or_load_run(
            definition,
            "run-durable",
            {"brief"},
            entity_id="lead-1",
            correlation_id="corr-1",
            input_payload={"brief": {"safe": True}},
        )
        replay = self.service.create_or_load_run(definition, "run-durable", {"brief"})
        self.assertEqual(replay.run_id, created.run_id)
        self.service.start_stage("run-durable", "prepare")
        self.service.record_attempt("run-durable", "prepare", {"worker": "worker-a", "verified": True})
        self.service.record_quality("run-durable", "prepare", {"passed": True, "checks": {"a": True}})

        restarted = WorkflowRunService(self.repository, self.event_log).load_run("run-durable")
        self.assertEqual(restarted.entity_id, "lead-1")
        self.assertEqual(restarted.correlation_id, "corr-1")
        self.assertEqual(restarted.input_payload, {"brief": {"safe": True}})
        self.assertEqual(restarted.stage("prepare").attempts[0]["worker"], "worker-a")
        self.assertTrue(restarted.stage("prepare").quality_result["passed"])
        self.assertFalse(restarted.external_action_taken)

    def test_quality_contract_prevents_false_completion(self) -> None:
        definition = workflow_definition_from_dict(
            {
                "workflow_id": "quality_guarded",
                "stages": [
                    {"stage_id": "prepare", "agent_ref": "worker-a", "quality_contract": "quality-a"}
                ],
            }
        )
        self.service.create_run(definition, "run-quality", set())
        self.service.start_stage("run-quality", "prepare")
        output = ArtifactRef("artifact-1", "draft", "runs/run-quality/draft.json")
        with self.assertRaisesRegex(ValueError, "quality contract cannot complete"):
            self.service.complete_stage("run-quality", "prepare", [output])
        self.service.record_quality("run-quality", "prepare", {"passed": True})
        completed = self.service.complete_stage("run-quality", "prepare", [output])
        self.assertEqual(completed.status, WorkflowStatus.COMPLETE)

    def test_interrupted_running_step_recovers_to_ready_without_claiming_execution(self) -> None:
        definition = workflow_definition_from_dict(
            {
                "workflow_id": "recoverable",
                "stages": [
                    {"stage_id": "prepare", "agent_ref": "worker-a", "required_inputs": ["brief"]}
                ],
            }
        )
        self.service.create_run(definition, "run-recover", {"brief"})
        self.service.start_stage("run-recover", "prepare")

        restarted = WorkflowRunService(self.repository, self.event_log)
        self.assertEqual(restarted.recover_interrupted_runs(), 1)
        recovered = restarted.load_run("run-recover")
        self.assertEqual(recovered.stage("prepare").status, StageStatus.READY)
        self.assertEqual(recovered.stage("prepare").retry_count, 1)
        self.assertFalse(recovered.external_action_taken)
        self.assertIn("stage.recovered", [event.event_type for event in self.event_log.read("run-recover")])


if __name__ == "__main__":
    unittest.main()
