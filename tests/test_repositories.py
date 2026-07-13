import tempfile
import unittest
from pathlib import Path

from runtime.models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog, RunNotFound, WorkflowEvent


class FileWorkflowRunRepositoryTests(unittest.TestCase):
    def test_round_trip_preserves_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = FileWorkflowRunRepository(Path(temporary) / "runs")
            state = WorkflowState(
                workflow_id="growth_blueprint_pipeline",
                run_id="run-001",
                stages=[
                    StageRecord(
                        stage_id="research_analyst",
                        agent_ref="agents/research_analyst.md",
                        status=StageStatus.COMPLETED,
                        required_inputs=("client_inputs",),
                        output_artifacts=[
                            ArtifactRef(
                                artifact_id="research-001",
                                artifact_type="completed_research_inputs",
                                location="runs/run-001/research.md",
                                metadata={"client": "Rave"},
                            )
                        ],
                        retry_count=1,
                        revision_count=2,
                    )
                ],
                status=WorkflowStatus.ACTIVE,
                current_stage_id="research_analyst",
            )

            repository.save(state)
            restored = repository.load("run-001")

            self.assertEqual(restored.run_id, state.run_id)
            self.assertEqual(restored.status, WorkflowStatus.ACTIVE)
            self.assertEqual(restored.stage("research_analyst").status, StageStatus.COMPLETED)
            self.assertEqual(restored.stage("research_analyst").retry_count, 1)
            self.assertEqual(restored.stage("research_analyst").revision_count, 2)
            self.assertEqual(
                restored.stage("research_analyst").output_artifacts[0].metadata,
                {"client": "Rave"},
            )

    def test_save_replaces_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = FileWorkflowRunRepository(temporary)
            state = WorkflowState(
                workflow_id="workflow",
                run_id="run-001",
                stages=[StageRecord("research", "agents/research.md")],
            )
            repository.save(state)
            state.status = WorkflowStatus.BLOCKED
            repository.save(state)
            self.assertEqual(repository.load("run-001").status, WorkflowStatus.BLOCKED)
            self.assertEqual(repository.list_run_ids(), ["run-001"])

    def test_missing_run_raises_specific_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = FileWorkflowRunRepository(temporary)
            with self.assertRaises(RunNotFound):
                repository.load("missing")

    def test_unsafe_run_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = FileWorkflowRunRepository(temporary)
            with self.assertRaises(ValueError):
                repository.exists("../escape")


class JsonlEventLogTests(unittest.TestCase):
    def test_events_are_appended_and_read_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            event_log = JsonlEventLog(temporary)
            first = WorkflowEvent.create(
                event_id="evt-001",
                run_id="run-001",
                event_type="workflow.initialised",
                payload={"status": "active"},
            )
            second = WorkflowEvent.create(
                event_id="evt-002",
                run_id="run-001",
                event_type="stage.started",
                payload={"stage_id": "research_analyst"},
            )
            event_log.append_many([first, second])

            events = event_log.read("run-001")

            self.assertEqual([event.event_id for event in events], ["evt-001", "evt-002"])
            self.assertTrue(event_log.contains("run-001", "evt-002"))

    def test_read_of_unknown_run_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(JsonlEventLog(temporary).read("unknown"), [])


if __name__ == "__main__":
    unittest.main()
