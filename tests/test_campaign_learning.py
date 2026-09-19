from __future__ import annotations

import tempfile
import unittest

from runtime.campaign_engine import CampaignIdentity
from runtime.campaign_learning import CampaignLearningError, CampaignLearningService, FileCampaignLearningStore
from runtime.execution_journal import ExecutionJournal
from runtime.media_control import CreativePlatformMapping, MediaControlService, MediaProvider
from tests.test_media_control import adapter, identity, mapping


ASSET_VERSION_ID = "NORTHSTAR-GB-CW01-VID-004"


def _snapshot_and_recommendations(directory: str):
    creative = CreativePlatformMapping(
        narratiive_asset_id=ASSET_VERSION_ID,
        campaign_world_id="northstar-cw-01",
        creative_territory="Own the next horizon",
        format="vertical_video",
        hook="Your next market is closer than it looks",
        message="Confident expansion",
        audience="UK growth leaders",
        provider=MediaProvider.TIKTOK,
        placement="for_you_feed",
        provider_creative_ids=("test-tiktok-creative",),
        provider_ad_ids=("test-tiktok-ad",),
    )
    service = MediaControlService(
        {MediaProvider.TIKTOK: adapter(MediaProvider.TIKTOK)},
        ExecutionJournal(directory),
    )
    snapshot = service.ingest(
        identity=identity(),
        provider_mapping=mapping(MediaProvider.TIKTOK),
        period_start="2026-09-10T00:00:00Z",
        period_end="2026-09-17T00:00:00Z",
        request_id="northstar-learning",
        tony_request="prepare bounded campaign learning",
        creative_mappings=(creative,),
    )
    return snapshot, service.analyse((snapshot,))


class CampaignLearningTests(unittest.TestCase):
    def test_performance_becomes_evidence_bound_insight_and_pending_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(directory)
            cycle = CampaignLearningService().build(
                (snapshot,),
                recommendations,
                approved_asset_version_ids=(ASSET_VERSION_ID,),
            )
            self.assertEqual(cycle.performance.mapped_asset_version_ids, (ASSET_VERSION_ID,))
            self.assertTrue(cycle.insights)
            self.assertTrue(cycle.iteration_proposals)
            self.assertTrue(all(item.human_review_required for item in cycle.insights))
            self.assertTrue(all(item.status == "pending_human_approval" for item in cycle.iteration_proposals))
            self.assertTrue(all(not item.production_authorised for item in cycle.iteration_proposals))
            self.assertTrue(all(not item.publication_authorised for item in cycle.iteration_proposals))
            self.assertTrue(all(not item.media_spend_authorised for item in cycle.iteration_proposals))
            self.assertTrue(cycle.notion_projection_required)
            self.assertFalse(cycle.external_action_taken)

    def test_unapproved_asset_mapping_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(directory)
            with self.assertRaisesRegex(CampaignLearningError, "unapproved"):
                CampaignLearningService().build(
                    (snapshot,),
                    recommendations,
                    approved_asset_version_ids=("different-approved-version",),
                )

    def test_mixed_campaign_evidence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(directory)
            other_identity = CampaignIdentity(
                workspace_id=snapshot.identity.workspace_id,
                client_id=snapshot.identity.client_id,
                brand_id=snapshot.identity.brand_id,
                market_ids=snapshot.identity.market_ids,
                product_ids=snapshot.identity.product_ids,
                campaign_id="different-campaign",
            )
            altered = type(snapshot)(
                identity=other_identity,
                provider=snapshot.provider,
                provider_mapping=snapshot.provider_mapping,
                period_start=snapshot.period_start,
                period_end=snapshot.period_end,
                currency=snapshot.currency,
                timezone_name=snapshot.timezone_name,
                campaign_status=snapshot.campaign_status,
                review_status=snapshot.review_status,
                tracking_status=snapshot.tracking_status,
                authorised_budget=snapshot.authorised_budget,
                metrics=snapshot.metrics,
                creative_mappings=snapshot.creative_mappings,
                breakdowns=snapshot.breakdowns,
                ingested_at=snapshot.ingested_at,
            )
            with self.assertRaisesRegex(CampaignLearningError, "canonical identity"):
                CampaignLearningService().build(
                    (snapshot, altered),
                    recommendations,
                    approved_asset_version_ids=(ASSET_VERSION_ID,),
                )

    def test_file_store_is_idempotent_and_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(directory)
            cycle = CampaignLearningService().build(
                (snapshot,), recommendations, approved_asset_version_ids=(ASSET_VERSION_ID,)
            )
            store = FileCampaignLearningStore(f"{directory}/learning")
            first = store.persist(cycle)
            second = store.persist(cycle)
            self.assertEqual(first, second)
            self.assertTrue(first.is_file())
            self.assertIn(cycle.checksum, first.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
