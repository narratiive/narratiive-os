from __future__ import annotations

import unittest

from runtime.delivery_follow_up_worker import (
    DeliveryFollowUpPreparationError,
    DeliveryFollowUpPreparationWorker,
)


def _contract() -> dict:
    return {
        "workflow_context": {"workflow_id": "delivery_to_follow_up_next_action"},
        "campaign_identity": {"campaign_id": "safe-campaign"},
        "verified_delivery_evidence": {
            "delivery_package_checksum": "a" * 64,
            "delivered_asset_version_ids": ["safe-asset-v1", "safe-asset-v2"],
        },
        "client_context": {"company": "SAFE Client"},
        "measurement_context": {"review_window": "after 14 days"},
    }


class DeliveryFollowUpPreparationWorkerTests(unittest.TestCase):
    def test_prepares_read_only_performance_and_iteration_plan(self) -> None:
        result = DeliveryFollowUpPreparationWorker()(_contract())
        self.assertEqual(result["performance_ingestion_plan"]["providers"], ["meta", "tiktok", "google"])
        self.assertEqual(result["iteration_control"]["strategy_authority"], "human")
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])

    def test_rejects_unverified_delivery_context(self) -> None:
        contract = _contract()
        contract["verified_delivery_evidence"]["delivered_asset_version_ids"] = []
        with self.assertRaisesRegex(DeliveryFollowUpPreparationError, "verified delivery"):
            DeliveryFollowUpPreparationWorker()(contract)


if __name__ == "__main__":
    unittest.main()
