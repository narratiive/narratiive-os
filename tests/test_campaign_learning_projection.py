from __future__ import annotations

import tempfile
import unittest

from runtime.campaign_learning import CampaignLearningService
from runtime.campaign_learning_projection import CampaignLearningProjectionService
from tests.test_campaign_learning import ASSET_VERSION_ID, _snapshot_and_recommendations


def _cycle(directory: str):
    snapshot, recommendations = _snapshot_and_recommendations(directory)
    return CampaignLearningService().build(
        (snapshot,), recommendations, approved_asset_version_ids=(ASSET_VERSION_ID,)
    )


class CampaignLearningProjectionTests(unittest.TestCase):
    def test_prepare_is_read_only_and_preserves_human_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cycle = _cycle(directory)
            projection = CampaignLearningProjectionService(f"{directory}/projection").prepare(cycle)
            self.assertEqual(projection["projection_status"], "prepared")
            self.assertEqual(projection["operational_status"], "learning_pending_human_review")
            self.assertTrue(all(item["human_review_required"] for item in projection["insights"]))
            self.assertTrue(all(item["status"] == "pending_human_approval" for item in projection["iteration_proposals"]))
            self.assertFalse(projection["publication_authorised"])
            self.assertFalse(projection["media_spend_authorised"])

    def test_sync_requires_explicit_approval_and_configured_notion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cycle = _cycle(directory)
            service = CampaignLearningProjectionService(f"{directory}/projection")
            with self.assertRaisesRegex(ValueError, "approval"):
                service.sync(cycle, approver="", rationale="")
            with self.assertRaisesRegex(ValueError, "Matt"):
                service.sync(cycle, approver="tony", rationale="Tony cannot project strategic learning.")
            result = service.sync(cycle, approver="telegram:matt", rationale="Project exact learning cycle.")
            self.assertEqual(result["projection_status"], "notion_dispatcher_unavailable")
            self.assertFalse(result["external_action_taken"])

    def test_verified_projection_is_idempotent(self) -> None:
        dispatches = []

        def notion(dispatch):
            dispatches.append(dispatch)
            payload = dispatch["payload"]
            return {
                "record_id": "notion-learning-record",
                "projection_key": dispatch["idempotency_key"],
                "cycle_checksum": payload["learning_cycle_checksum"],
                "external_action_taken": True,
            }

        with tempfile.TemporaryDirectory() as directory:
            cycle = _cycle(directory)
            service = CampaignLearningProjectionService(f"{directory}/projection", notion)
            first = service.sync(cycle, approver="telegram:matt", rationale="Project exact learning cycle.")
            second = service.sync(cycle, approver="telegram:matt", rationale="Repeat safely.")
            self.assertEqual(first["projection_status"], "verified")
            self.assertEqual(second["projection_status"], "duplicate_suppressed")
            self.assertEqual(len(dispatches), 1)
            self.assertEqual(dispatches[0]["execution_mode"], "approval_gated_write")
            self.assertFalse(dispatches[0]["payload"]["publication_authorised"])
            self.assertFalse(dispatches[0]["payload"]["media_spend_authorised"])

    def test_unverified_notion_evidence_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cycle = _cycle(directory)
            service = CampaignLearningProjectionService(
                f"{directory}/projection",
                lambda _dispatch: {
                    "record_id": "notion-learning-record",
                    "projection_key": "wrong-key",
                    "cycle_checksum": cycle.checksum,
                    "external_action_taken": True,
                },
            )
            result = service.sync(cycle, approver="telegram:matt", rationale="Project exact learning cycle.")
            self.assertEqual(result["projection_status"], "reconciliation_required")
            self.assertFalse(result["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
