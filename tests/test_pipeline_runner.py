import json
import tempfile
import unittest
from pathlib import Path

from runtime.definitions import load_workflow_definition
from runtime.dispatch import FileDispatchQueue
from runtime.execution_package import ExecutionPackageBuilder
from runtime.memory import (
    FileMemoryStore,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    SpecialistMemorySelector,
)
from runtime.models import StageStatus, WorkflowStatus
from runtime.pipeline_runner import DeterministicProvider, PipelineRunner, load_pipeline_fixture
from runtime.provider import ArtifactWriter, ProviderExecutor
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.scoring import ConfidenceEngine
from runtime.specialists import SpecialistCatalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / "workflows/growth_blueprint_pipeline.json"
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/rave_pipeline.json"


class FailOnceProvider:
    def __init__(self, provider, stage_id):
        self.provider = provider
        self.stage_id = stage_id
        self.failed = False

    @property
    def calls(self):
        return self.provider.calls

    def generate(self, package):
        if package.stage_id == self.stage_id and not self.failed:
            self.failed = True
            self.provider.calls.append(package.stage_id)
            raise RuntimeError("synthetic provider interruption")
        return self.provider.generate(package)


class PipelineRunnerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fixture = load_pipeline_fixture(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.runs = FileWorkflowRunRepository(self.root / "runs")
        self.events = JsonlEventLog(self.root / "events")
        self.queue = FileDispatchQueue(self.root / "jobs")
        catalog = SpecialistCatalog(REPOSITORY_ROOT, WORKFLOW_PATH)
        self.output_types = {
            stage.stage_id: catalog.output_type(manifest)
            for stage, manifest in zip(catalog.workflow.stages, catalog.manifests())
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_runner(
        self,
        provider,
        memory_selector=None,
        confidence_engine=None,
    ):
        executor = ProviderExecutor(
            package_builder=ExecutionPackageBuilder(
                REPOSITORY_ROOT,
                self.output_types,
                memory_selector=memory_selector,
                confidence_engine=confidence_engine,
            ),
            provider=provider,
            artifact_writer=ArtifactWriter(self.root / "artifacts"),
        )
        return PipelineRunner(
            definition=load_workflow_definition(WORKFLOW_PATH),
            runs=self.runs,
            event_log=self.events,
            queue=self.queue,
            executor=executor,
        )

    def test_executes_all_five_stages_with_traceable_artifacts(self) -> None:
        provider = DeterministicProvider.from_fixture(self.fixture)
        state = self.make_runner(provider).run(
            "rave-integration",
            self.fixture["available_inputs"],
        )

        expected_stages = [stage.stage_id for stage in state.stages]
        self.assertEqual(provider.calls, expected_stages)
        self.assertEqual(state.status, WorkflowStatus.COMPLETE)
        self.assertTrue(all(stage.status == StageStatus.COMPLETED for stage in state.stages))

        for index, stage in enumerate(state.stages):
            artifact = stage.output_artifacts[0]
            self.assertTrue(Path(artifact.location).is_file())
            self.assertTrue(artifact.checksum)
            if index + 1 < len(state.stages):
                self.assertEqual(state.stages[index + 1].input_artifacts, [artifact])
                downstream_artifact = state.stages[index + 1].output_artifacts[0]
                self.assertEqual(
                    downstream_artifact.metadata["input_artifact_ids"],
                    [artifact.artifact_id],
                )

        final_artifact = state.stages[-1].output_artifacts[0]
        self.assertIn("Verdict: APPROVE", Path(final_artifact.location).read_text(encoding="utf-8"))
        completed = [
            event.payload["stage_id"]
            for event in self.events.read(state.run_id)
            if event.event_type == "stage.completed"
        ]
        self.assertEqual(completed, expected_stages)

    def test_duplicate_execution_reuses_completed_run(self) -> None:
        provider = DeterministicProvider.from_fixture(self.fixture)
        runner = self.make_runner(provider)
        first = runner.run("rave-idempotent", self.fixture["available_inputs"])
        event_count = len(self.events.read(first.run_id))

        second = runner.run("rave-idempotent", self.fixture["available_inputs"])

        self.assertEqual(second.status, WorkflowStatus.COMPLETE)
        self.assertEqual(len(provider.calls), 5)
        self.assertEqual(len(self.events.read(second.run_id)), event_count)

    def test_retry_resumes_without_repeating_completed_stages(self) -> None:
        provider = FailOnceProvider(
            DeterministicProvider.from_fixture(self.fixture),
            "campaign_world_generator",
        )
        runner = self.make_runner(provider)
        interrupted = runner.run("rave-resume", self.fixture["available_inputs"])
        first_artifact_ids = [
            stage.output_artifacts[0].artifact_id
            for stage in interrupted.stages[:2]
        ]

        self.assertEqual(
            interrupted.stage("campaign_world_generator").status,
            StageStatus.RETRY_REQUIRED,
        )
        resumed = runner.run("rave-resume", self.fixture["available_inputs"])

        self.assertEqual(resumed.status, WorkflowStatus.COMPLETE)
        self.assertEqual(
            [stage.output_artifacts[0].artifact_id for stage in resumed.stages[:2]],
            first_artifact_ids,
        )
        self.assertEqual(provider.calls[:2], ["research_analyst", "strategy_director"])
        self.assertEqual(provider.calls.count("campaign_world_generator"), 2)
        completed = [
            event.payload["stage_id"]
            for event in self.events.read(resumed.run_id)
            if event.event_type == "stage.completed"
        ]
        self.assertEqual(completed.count("research_analyst"), 1)
        self.assertEqual(completed.count("strategy_director"), 1)

    def test_specialists_receive_only_selected_memory(self) -> None:
        memory_store = FileMemoryStore(self.root / "memory")
        memory_store.append(
            MemoryRecord(
                memory_id="brand-context",
                client_id="rave",
                kind=MemoryKind.CONTEXT,
                scope=MemoryScope.CLIENT,
                content="RAVE brand context",
            )
        )
        memory_store.append(
            MemoryRecord(
                memory_id="run-evidence",
                client_id="rave",
                run_id="rave-memory",
                kind=MemoryKind.EVIDENCE,
                scope=MemoryScope.RUN,
                content="RAVE run evidence",
            )
        )
        provider = DeterministicProvider.from_fixture(self.fixture)
        state = self.make_runner(
            provider,
            memory_selector=SpecialistMemorySelector(memory_store),
        ).run(
            "rave-memory",
            self.fixture["available_inputs"],
            client_id="rave",
        )

        memory_ids = {
            stage.stage_id: stage.output_artifacts[0].metadata["memory_ids"]
            for stage in state.stages
        }
        self.assertEqual(
            memory_ids["research_analyst"],
            ["brand-context", "run-evidence"],
        )
        self.assertEqual(memory_ids["campaign_world_generator"], ["brand-context"])
        self.assertEqual(memory_ids["creative_director"], ["brand-context"])
        self.assertEqual(
            memory_ids["quality_reviewer"],
            ["brand-context", "run-evidence"],
        )

    def test_quality_reviewer_receives_advisory_scorecard(self) -> None:
        provider = DeterministicProvider.from_fixture(self.fixture)
        state = self.make_runner(
            provider,
            confidence_engine=ConfidenceEngine(),
        ).run(
            "rave-scorecard",
            self.fixture["available_inputs"],
            client_id="rave",
            scoring_input=self.fixture["scoring_input"],
        )

        recommendations = {
            stage.stage_id: stage.output_artifacts[0].metadata[
                "scorecard_recommendation"
            ]
            for stage in state.stages
        }
        self.assertTrue(
            all(
                recommendation is None
                for stage_id, recommendation in recommendations.items()
                if stage_id != "quality_reviewer"
            )
        )
        self.assertEqual(recommendations["quality_reviewer"], "approve")
        quality_metadata = state.stage("quality_reviewer").output_artifacts[0].metadata
        scorecard = quality_metadata["confidence_scorecard"]
        self.assertEqual(scorecard["recommendation"], "approve")
        self.assertEqual(len(scorecard["input_checksum"]), 64)
        self.assertTrue(scorecard["overall_risk"]["reasons"])

    def test_fixture_requires_stage_outputs(self) -> None:
        with self.assertRaises(ValueError):
            DeterministicProvider.from_fixture(json.loads("{}"))


if __name__ == "__main__":
    unittest.main()
