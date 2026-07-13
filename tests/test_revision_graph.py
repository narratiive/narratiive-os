import json
import tempfile
import unittest
from pathlib import Path

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.definitions import load_workflow_definition
from runtime.dispatch import FileDispatchQueue
from runtime.execution_package import ExecutionPackageBuilder
from runtime.models import StageStatus, WorkflowStatus
from runtime.pipeline_runner import DeterministicProvider, PipelineRunner
from runtime.provider import ArtifactWriter, ProviderExecutor
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.revision_graph import (
    RevisionCategory,
    RevisionIssue,
    RevisionOwner,
    RevisionService,
    RevisionSeverity,
)
from runtime.specialists import SpecialistCatalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / "workflows/growth_blueprint_pipeline.json"
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/rave_pipeline.json"


class RevisionGraphIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runs = FileWorkflowRunRepository(self.root / "runs")
        self.events = JsonlEventLog(self.root / "events")
        self.queue = FileDispatchQueue(self.root / "jobs")
        self.artifacts = FileArtifactCatalog(self.root / "catalog")
        self.definition = load_workflow_definition(WORKFLOW_PATH)
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.outputs = fixture["stage_outputs"]
        catalog = SpecialistCatalog(REPOSITORY_ROOT, WORKFLOW_PATH)
        self.output_types = {
            stage.stage_id: catalog.output_type(manifest)
            for stage, manifest in zip(
                catalog.workflow.stages,
                catalog.manifests(),
            )
        }
        self._complete_initial_run()
        self.records = {
            stage.stage_id: self.artifacts.history(
                "run-1",
                stage.stage_id,
                self.output_types[stage.stage_id],
            )[-1]
            for stage in self.definition.stages
        }
        self.revisions = RevisionService(
            self.runs,
            self.events,
            self.artifacts,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _runner(self, provider):
        return PipelineRunner(
            definition=self.definition,
            runs=self.runs,
            event_log=self.events,
            queue=self.queue,
            executor=ProviderExecutor(
                package_builder=ExecutionPackageBuilder(
                    REPOSITORY_ROOT,
                    self.output_types,
                ),
                provider=provider,
                artifact_writer=ArtifactWriter(self.root / "outputs"),
                artifact_catalog=self.artifacts,
            ),
        )

    def _complete_initial_run(self):
        self.initial_provider = DeterministicProvider(self.outputs)
        state = self._runner(self.initial_provider).run(
            "run-1",
            {"client_inputs", "source_material"},
        )
        self.assertEqual(state.status, WorkflowStatus.AWAITING_APPROVAL)

    def _rerun(self, available_inputs=None):
        provider = DeterministicProvider(self.outputs)
        state = self._runner(provider).run(
            "run-1",
            available_inputs or {"client_inputs", "source_material"},
        )
        return state, provider

    def test_strategy_revision_invalidates_and_reruns_only_downstream(self):
        before = self.runs.load("run-1")
        research_artifact_id = before.stage(
            "research_analyst"
        ).output_artifacts[0].artifact_id
        issue = RevisionIssue(
            revision_id="rev-strategy",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.CREATIVE,
            severity=RevisionSeverity.MAJOR,
            reason="Positioning is not sufficiently specific.",
            affected_artifact_ids=(
                self.records["strategy_director"].artifact.artifact_id,
            ),
        )

        plan = self.revisions.request_revision(issue)
        invalidated = self.runs.load("run-1")

        self.assertEqual(plan.owner_stage_id, "strategy_director")
        self.assertEqual(
            plan.invalidated_stage_ids,
            (
                "strategy_director",
                "campaign_world_generator",
                "creative_director",
                "quality_reviewer",
            ),
        )
        self.assertEqual(
            invalidated.stage("research_analyst").output_artifacts[0].artifact_id,
            research_artifact_id,
        )
        self.assertEqual(
            invalidated.stage("strategy_director").status,
            StageStatus.READY,
        )
        self.assertEqual(
            invalidated.stage("research_analyst").revision_count,
            0,
        )
        self.assertTrue(
            all(
                invalidated.stage(stage_id).revision_count == 1
                for stage_id in plan.invalidated_stage_ids
            )
        )
        self.assertTrue(
            all(
                invalidated.stage(stage_id).status == StageStatus.NOT_STARTED
                for stage_id in plan.invalidated_stage_ids[1:]
            )
        )

        completed, provider = self._rerun()
        self.assertEqual(
            provider.calls,
            [
                "strategy_director",
                "campaign_world_generator",
                "creative_director",
                "quality_reviewer",
            ],
        )
        self.assertEqual(completed.status, WorkflowStatus.AWAITING_APPROVAL)
        self.assertTrue(
            (self.root / "jobs" / "run-1--strategy_director--revision-1.json").is_file()
        )

    def test_creative_revision_preserves_strategy_and_campaign(self):
        before = self.runs.load("run-1")
        preserved = {
            stage_id: before.stage(stage_id).output_artifacts[0].artifact_id
            for stage_id in (
                "research_analyst",
                "strategy_director",
                "campaign_world_generator",
            )
        }
        issue = RevisionIssue(
            revision_id="rev-creative",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.CREATIVE,
            severity=RevisionSeverity.MAJOR,
            reason="Production direction is ambiguous.",
            affected_artifact_ids=(
                self.records["creative_director"].artifact.artifact_id,
            ),
        )

        plan = self.revisions.request_revision(issue)
        state, provider = self._rerun()

        self.assertEqual(plan.owner_stage_id, "creative_director")
        self.assertEqual(
            plan.invalidated_stage_ids,
            ("creative_director", "quality_reviewer"),
        )
        self.assertEqual(provider.calls, ["creative_director", "quality_reviewer"])
        for stage_id, artifact_id in preserved.items():
            self.assertEqual(
                state.stage(stage_id).output_artifacts[0].artifact_id,
                artifact_id,
            )

    def test_blocked_evidence_revision_waits_for_required_input(self):
        issue = RevisionIssue(
            revision_id="rev-evidence",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.EVIDENCE,
            severity=RevisionSeverity.CRITICAL,
            reason="Product proof is unsupported.",
            evidence_requirement="validated_product_proof",
            blocking=True,
        )

        plan = self.revisions.request_revision(issue)
        blocked, blocked_provider = self._rerun()

        self.assertEqual(plan.owner_stage_id, "research_analyst")
        self.assertEqual(blocked.status, WorkflowStatus.BLOCKED)
        self.assertEqual(
            blocked.stage("research_analyst").missing_inputs,
            ["validated_product_proof"],
        )
        self.assertEqual(blocked_provider.calls, [])

        completed, provider = self._rerun(
            {
                "client_inputs",
                "source_material",
                "validated_product_proof",
            }
        )
        self.assertEqual(completed.status, WorkflowStatus.AWAITING_APPROVAL)
        self.assertEqual(
            provider.calls,
            [stage.stage_id for stage in self.definition.stages],
        )

    def test_every_invalidation_is_event_logged(self):
        issue = RevisionIssue(
            revision_id="rev-events",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.CREATIVE,
            severity=RevisionSeverity.MINOR,
            reason="Creative rules need clarification.",
            owner=RevisionOwner.CREATIVE_DIRECTOR,
        )

        plan = self.revisions.request_revision(issue)
        invalidations = [
            event
            for event in self.events.read("run-1")
            if event.event_type == "stage.invalidated"
            and event.payload["revision_id"] == issue.revision_id
        ]

        self.assertEqual(
            [event.payload["stage_id"] for event in invalidations],
            list(plan.invalidated_stage_ids),
        )
        self.assertTrue(
            all("previous_output_artifact_ids" in event.payload for event in invalidations)
        )

    def test_previous_artifact_versions_remain_available(self):
        creative = self.records["creative_director"]
        issue = RevisionIssue(
            revision_id="rev-history",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.CREATIVE,
            severity=RevisionSeverity.MAJOR,
            reason="Creative artifact needs a new version.",
            affected_artifact_ids=(creative.artifact.artifact_id,),
        )
        self.revisions.request_revision(issue)

        self._rerun()
        history = self.artifacts.history(
            "run-1",
            "creative_director",
            self.output_types["creative_director"],
        )

        self.assertEqual([record.version for record in history], [1, 2])
        self.assertEqual(history[0].artifact.artifact_id, creative.artifact.artifact_id)
        self.assertTrue(Path(creative.artifact.location).is_file())


class RevisionIssueTests(unittest.TestCase):
    def test_round_trips_machine_readable_issue(self):
        issue = RevisionIssue(
            revision_id="rev-1",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.STRATEGY,
            severity=RevisionSeverity.MAJOR,
            reason="Strategy requires revision.",
            owner=RevisionOwner.STRATEGY_DIRECTOR,
            affected_artifact_ids=("artifact-1",),
        )
        self.assertEqual(RevisionIssue.from_dict(issue.to_dict()), issue)

    def test_blocking_evidence_requires_requirement(self):
        with self.assertRaises(ValueError):
            RevisionIssue(
                revision_id="rev-1",
                run_id="run-1",
                source_stage_id="quality_reviewer",
                category=RevisionCategory.EVIDENCE,
                severity=RevisionSeverity.CRITICAL,
                reason="Evidence is missing.",
                blocking=True,
            )


if __name__ == "__main__":
    unittest.main()
