import tempfile
import unittest
from pathlib import Path

from runtime.definitions import StageDefinition, WorkflowDefinition
from runtime.dispatch import DispatchJob, FileDispatchQueue, JobStatus, LeaseConflict
from runtime.dispatch_service import DispatchService
from runtime.models import ArtifactRef, StageStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.run_service import WorkflowRunService


class FileDispatchQueueTests(unittest.TestCase):
    def test_enqueue_is_idempotent_for_same_job_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = FileDispatchQueue(tmp)
            job = DispatchJob("job-1", "run-1", "research", "agents/research.md", {})
            first = queue.enqueue(job)
            second = queue.enqueue(job)
            self.assertEqual(first.job_id, second.job_id)

    def test_lease_complete_and_duplicate_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = FileDispatchQueue(tmp)
            queue.enqueue(DispatchJob("job-1", "run-1", "research", "agents/research.md", {}))
            leased = queue.lease_next("worker-a", 60)
            self.assertIsNotNone(leased)
            self.assertEqual(leased.status, JobStatus.LEASED)
            completed = queue.complete("job-1", "worker-a", {"ok": True})
            self.assertEqual(completed.status, JobStatus.COMPLETED)
            duplicate = queue.complete("job-1", "worker-b", {"ignored": True})
            self.assertEqual(duplicate.result, {"ok": True})

    def test_wrong_worker_cannot_complete_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = FileDispatchQueue(tmp)
            queue.enqueue(DispatchJob("job-1", "run-1", "research", "agents/research.md", {}))
            queue.lease_next("worker-a", 60)
            with self.assertRaises(LeaseConflict):
                queue.complete("job-1", "worker-b", {})

    def test_retryable_failure_returns_job_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = FileDispatchQueue(tmp)
            queue.enqueue(DispatchJob("job-1", "run-1", "research", "agents/research.md", {}))
            queue.lease_next("worker-a", 60)
            failed = queue.fail("job-1", "worker-a", "timeout", True)
            self.assertEqual(failed.status, JobStatus.PENDING)
            self.assertIsNone(failed.leased_by)


class DispatchServiceTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_dispatch_lifecycle_advances_workflow(self) -> None:
        job = self.dispatch.enqueue_current_stage("run-1")
        self.assertEqual(job.stage_id, "research")
        leased = self.dispatch.lease_next("worker-a", 60)
        self.assertEqual(leased.job_id, job.job_id)
        self.assertEqual(self.runs.load("run-1").stage("research").status, StageStatus.RUNNING)

        artifact = ArtifactRef("research-1", "completed_research", "runs/run-1/research.md")
        state = self.dispatch.complete_job(
            job.job_id,
            "worker-a",
            [artifact],
            {"completed_research"},
        )
        self.assertEqual(state.stage("research").status, StageStatus.COMPLETED)
        self.assertEqual(state.stage("strategy").status, StageStatus.READY)
        self.assertEqual(self.queue.get(job.job_id).status, JobStatus.COMPLETED)

        event_types = [event.event_type for event in self.events.read("run-1")]
        self.assertIn("dispatch.enqueued", event_types)
        self.assertIn("dispatch.leased", event_types)
        self.assertIn("dispatch.completed", event_types)

    def test_retryable_worker_failure_requests_stage_retry(self) -> None:
        job = self.dispatch.enqueue_current_stage("run-1")
        self.dispatch.lease_next("worker-a", 60)
        state = self.dispatch.fail_job(job.job_id, "worker-a", "provider timeout", True)
        self.assertEqual(state.stage("research").status, StageStatus.RETRY_REQUIRED)
        self.assertEqual(self.queue.get(job.job_id).status, JobStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
