from __future__ import annotations

import tempfile
import unittest

from runtime.campaign_engine import (
    CampaignEngine,
    CampaignEngineApplicationService,
    FileCampaignEngineRepository,
    ProductionDispatchApproval,
    ProductionJobRoute,
)
from runtime.campaign_production_executor import (
    CampaignProductionExecutor,
    ProductionExecutionError,
    ProductionExecutionRecoveryRequired,
)
from runtime.execution_journal import ExecutionJournal
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    NoAvailableWorker,
    WorkerAvailability,
    WorkerMetadata,
    WorkerRegistration,
)
from tests.test_campaign_engine import (
    approval,
    artifact,
    candidate,
    planned_asset_manifest,
    production_plan,
    quality,
    state,
    tony,
)


def approved_dispatch_state(*, approve_dispatch: bool = True):
    engine = CampaignEngine()
    current = engine.commission_campaign_worlds(state())
    current = engine.submit_campaign_worlds(
        current,
        (candidate("a", "checksum-a"), candidate("b", "checksum-b")),
    )
    for candidate_id, checksum in (("a", "checksum-a"), ("b", "checksum-b")):
        current = engine.review_campaign_world(
            current,
            candidate_id,
            quality_review=quality(checksum),
            tony_review=tony(checksum),
        )
    selected = current.campaign_world_candidates[0].artifact
    current = engine.select_campaign_world(current, "a", approval(selected))
    bible = artifact("bible-1", "creative_directors_bible", "bible-checksum")
    current = engine.submit_creative_bible(current, bible)
    current = engine.review_creative_bible(
        current,
        quality_review=quality(bible.checksum),
        tony_review=tony(bible.checksum),
    )
    current = engine.approve_creative_bible(current, approval(bible))
    plan = production_plan(bible)
    current = engine.submit_production_plan(current, plan)
    current = engine.approve_production_plan(current, approval(plan.production_pack))
    current = engine.start_asset_production(current, planned_asset_manifest(plan))
    job = plan.jobs[0]
    current = engine.register_production_route(
        current,
        ProductionJobRoute(
            route_id="route-video-1",
            job_id=job.job_id,
            required_capability=job.required_capability,
            worker_id="video-worker",
            provider="synthetic-provider",
            policy_id="synthetic-policy",
            selection_reason="only_eligible_worker",
            source_production_pack_checksum=plan.production_pack.checksum,
        ),
    )
    current = engine.prepare_production_dispatch(
        current,
        route_id="route-video-1",
        dispatch_id="dispatch-video-1",
        production_parameters={"prompt": "Synthetic approved prompt", "variants": 3},
    )
    if approve_dispatch:
        preview = current.production_dispatch_previews[0]
        current = engine.approve_production_dispatch(
            current,
            ProductionDispatchApproval(
                approver="matt",
                rationale="Approved this exact synthetic production request.",
                dispatch_id=preview.dispatch_id,
                payload_checksum=preview.payload_checksum,
            ),
        )
    return current


def production_result(current) -> dict:
    asset = current.asset_manifest.assets[0]
    return {
        "verified": True,
        "external_action_taken": True,
        "publication_authorised": False,
        "media_spend_authorised": False,
        "delivery_authorised": False,
        "provider_receipt_id": "synthetic-receipt-1",
        "asset_version": {
            "asset_version_id": f"{asset.asset_id}-v1",
            "asset_id": asset.asset_id,
            "version_number": 1,
            "file_checksum": "synthetic-file-checksum-1",
            "drive_uri": f"drive://synthetic-campaign/{asset.asset_id}/v1.mp4",
            "producer": "synthetic-provider",
            "production_job_id": asset.production_job_id,
            "source_manifest_checksum": current.asset_manifest.manifest_artifact.checksum,
        },
    }


class CampaignProductionExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repository = FileCampaignEngineRepository(self.tempdir.name, workspace_id="agency")
        self.application = CampaignEngineApplicationService(self.repository)
        self.journal = ExecutionJournal(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @staticmethod
    def registry(adapter, *, permissions=("preparation", "external_write")):
        return CapabilityWorkerRegistry(
            (
                WorkerRegistration(
                    WorkerMetadata(
                        worker_id="video-worker",
                        provider="synthetic-provider",
                        capabilities=("short_form_video_production",),
                        availability=WorkerAvailability.AVAILABLE,
                        side_effect_permissions=permissions,
                    ),
                    adapter,
                ),
            )
        )

    def executor(self, adapter, *, permissions=("preparation", "external_write")):
        return CampaignProductionExecutor(
            registry=self.registry(adapter, permissions=permissions),
            application=self.application,
            journal=self.journal,
        )

    def test_exact_approval_executes_once_and_persists_unapproved_drive_version(self) -> None:
        current = approved_dispatch_state()
        self.repository.save(current, transition_id="synthetic-seed")
        calls = []
        executor = self.executor(lambda contract: calls.append(contract) or production_result(current))

        persisted, replay = executor.execute(
            current,
            dispatch_id="dispatch-video-1",
            transition_id="execute-dispatch-video-1",
        )

        self.assertFalse(replay)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["execution_mode"], "approved_production")
        self.assertEqual(calls[0]["approval"]["approver"], "matt")
        self.assertEqual(calls[0]["payload_checksum"], current.production_dispatch_previews[0].payload_checksum)
        self.assertEqual(len(persisted.asset_versions), 1)
        self.assertTrue(persisted.asset_versions[0].human_review_required)
        self.assertFalse(persisted.asset_versions[0].publication_authorised)
        self.assertFalse(persisted.asset_versions[0].delivery_authorised)
        self.assertEqual(self.repository.load("safe-client", "safe-campaign"), persisted)
        self.assertEqual([record.status for record in self.journal.read_all()], ["dispatched", "completed"])

        replayed, replay = executor.execute(
            persisted,
            dispatch_id="dispatch-video-1",
            transition_id="execute-dispatch-video-1",
        )
        self.assertTrue(replay)
        self.assertEqual(replayed, persisted)
        self.assertEqual(len(calls), 1)

    def test_execution_requires_matt_approval_before_worker_call(self) -> None:
        current = approved_dispatch_state(approve_dispatch=False)
        calls = []
        executor = self.executor(lambda contract: calls.append(contract) or production_result(current))

        with self.assertRaisesRegex(Exception, "exact-payload approval"):
            executor.execute(
                current,
                dispatch_id="dispatch-video-1",
                transition_id="execute-without-approval",
            )
        self.assertEqual(calls, [])
        self.assertEqual(self.journal.read_all(), [])

    def test_worker_requires_explicit_external_write_capability(self) -> None:
        current = approved_dispatch_state()
        executor = self.executor(lambda contract: production_result(current), permissions=("preparation",))

        with self.assertRaisesRegex(NoAvailableWorker, "not configured for production execution"):
            executor.execute(
                current,
                dispatch_id="dispatch-video-1",
                transition_id="execute-without-write-capability",
            )
        self.assertEqual(self.journal.read_all(), [])

    def test_malformed_or_overreaching_result_fails_closed_and_blocks_automatic_retry(self) -> None:
        current = approved_dispatch_state()
        self.repository.save(current, transition_id="synthetic-seed")
        result = production_result(current)
        result["publication_authorised"] = True
        calls = []
        executor = self.executor(lambda contract: calls.append(contract) or result)

        with self.assertRaisesRegex(ProductionExecutionError, "deny publication, delivery and media-spend"):
            executor.execute(
                current,
                dispatch_id="dispatch-video-1",
                transition_id="execute-overreach",
            )
        self.assertEqual([record.status for record in self.journal.read_all()], ["dispatched", "failed"])
        with self.assertRaisesRegex(ProductionExecutionRecoveryRequired, "reconcile"):
            executor.execute(
                current,
                dispatch_id="dispatch-video-1",
                transition_id="execute-overreach",
            )
        self.assertEqual(len(calls), 1)

    def test_completed_receipt_recovers_after_campaign_state_persistence_failure(self) -> None:
        current = approved_dispatch_state()
        self.repository.save(current, transition_id="synthetic-seed")
        calls = []

        class FailingApplication:
            def persist_transition(self, expected, proposed, *, transition_id):
                raise RuntimeError("synthetic persistence interruption")

        interrupted = CampaignProductionExecutor(
            registry=self.registry(lambda contract: calls.append(contract) or production_result(current)),
            application=FailingApplication(),
            journal=self.journal,
        )
        with self.assertRaisesRegex(RuntimeError, "persistence interruption"):
            interrupted.execute(
                current,
                dispatch_id="dispatch-video-1",
                transition_id="execute-recovery",
            )
        self.assertEqual(self.journal.latest("production:agency:safe-client:safe-campaign:dispatch-video-1").status, "completed")

        recovered, replay = self.executor(
            lambda contract: self.fail("provider must not be called during receipt recovery")
        ).execute(
            current,
            dispatch_id="dispatch-video-1",
            transition_id="execute-recovery",
        )
        self.assertTrue(replay)
        self.assertEqual(len(recovered.asset_versions), 1)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
