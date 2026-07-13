import tempfile
import unittest
from pathlib import Path

from runtime.definitions import StageDefinition, WorkflowDefinition
from runtime.dispatch import FileDispatchQueue, JobStatus
from runtime.dispatch_service import DispatchService
from runtime.models import StageStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.run_service import WorkflowRunService
from runtime.worker import AgentExecutor, ExecutionResult, JsonArtifactExecutor, WorkerRunner


class FailingExecutor:
    def execute(self, job):
        raise RuntimeError("temporary provider failure")


class WorkerRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs = FileWorkflowRunRepository(root / "runs")
        self.events = JsonlEventLog(root / "events")
        self.queue = FileDispatchQueue(root / "jobs")
        self.run_service = WorkflowRunService(self.runs, self.events)
        self.dispatch = DispatchService(self.runs, self.events, self.queue, self.run_service)
        self.definition = WorkflowDefinition(
            workflow_id="test_pipeline",
            stages=(
                StageDefinition("research", "agents/research.md", ("client_inputs",)),
                StageDefinition("strategy", "agents/strategy.md", ("completed_research",)),
            ),
        )
        self.run_service.create_run(self.definition, "run-1", {"client_inputs"})
        self.dispatch.enqueue_current_stage("run-1")
        self.root = root

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_reference_worker_executes_and_advances_run(self) -> None:
        executor = JsonArtifactExecutor(
            self.root / "artifacts",
            {"research": "completed_research"},
        )
        runner = WorkerRunner(
            worker_id="worker-local",
            dispatcher=self.dispatch,
            executor=executor,
            lease_seconds=60,
        )
        job = runner.run_once()
        self.assertIsNotNone(job)
        state = self.runs.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.COMPLETED)
        self.assertEqual(state.stage("strategy").status, StageStatus.READY)
        self.assertEqual(self.queue.get(job.job_id).status, JobStatus.COMPLETED)
        self.assertTrue((self.root / "artifacts" / "run-1" / "research.json").exists())

    def test_worker_failure_returns_job_for_retry(self) -> None:
        runner = WorkerRunner(
            worker_id="worker-local",
            dispatcher=self.dispatch,
            executor=FailingExecutor(),
            lease_seconds=60,
        )
        job = runner.run_once()
        state = self.runs.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.RETRY_REQUIRED)
        self.assertEqual(self.queue.get(job.job_id).status, JobStatus.PENDING)

    def test_run_once_returns_none_when_queue_empty(self) -> None:
        empty_root = self.root / "empty"
        empty_queue = FileDispatchQueue(empty_root / "jobs")
        empty_dispatch = DispatchService(self.runs, self.events, empty_queue, self.run_service)
        runner = WorkerRunner(
            worker_id="worker-local",
            dispatcher=empty_dispatch,
            executor=FailingExecutor(),
        )
        self.assertIsNone(runner.run_once())


if __name__ == "__main__":
    unittest.main()
