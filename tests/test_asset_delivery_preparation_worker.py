from __future__ import annotations

import unittest

from runtime.asset_delivery_preparation_worker import (
    AssetDeliveryPreparationError,
    AssetDeliveryPreparationWorker,
)


def _contract() -> dict:
    suite_checksum = "a" * 64
    assets = []
    planned = []
    for index in range(1, 3):
        asset_id = f"safe-asset-{index}"
        job_id = f"safe-job-{index}"
        version_id = f"{asset_id}-v1"
        planned.append({"asset_id": asset_id, "production_job_id": job_id})
        assets.append(
            {
                "asset_version_id": version_id,
                "asset_id": asset_id,
                "production_job_id": job_id,
                "file_checksum": str(index) * 64,
                "drive_uri": f"drive://safe/{version_id}",
                "status": "approved",
                "approval_status": "approved",
                "source_asset_suite_checksum": suite_checksum,
            }
        )
    return {
        "workflow_context": {"workflow_id": "asset_review_to_delivery_preparation"},
        "campaign_identity": {
            "workspace_id": "agency",
            "client_id": "safe-client",
            "brand_id": "safe-brand",
            "market_ids": ["uk"],
            "product_ids": ["safe-product"],
            "campaign_id": "safe-campaign",
        },
        "reviewed_assets": assets,
        "asset_manifest": {"manifest_id": "safe-manifest", "assets": planned},
        "asset_suite_approval": {
            "decision": "asset_suite_approval",
            "approver": "telegram:matt",
            "asset_suite_checksum": suite_checksum,
            "asset_version_ids": [item["asset_version_id"] for item in assets],
        },
        "delivery_requirements": {"destination": "safe client Drive folder"},
    }


class AssetDeliveryPreparationWorkerTests(unittest.TestCase):
    def test_builds_deterministic_non_delivering_package(self) -> None:
        worker = AssetDeliveryPreparationWorker()
        first = worker(_contract())
        second = worker(_contract())
        self.assertEqual(first, second)
        self.assertEqual(first["delivery_manifest"]["asset_count"], 2)
        self.assertEqual(
            first["proposed_delivery_action"]["delivery_package_checksum"],
            first["delivery_package"]["checksum"],
        )
        self.assertFalse(first["external_action_taken"])
        self.assertFalse(first["delivery_authorised"])

    def test_rejects_unapproved_or_partial_asset_suite(self) -> None:
        contract = _contract()
        contract["reviewed_assets"].pop()
        with self.assertRaisesRegex(AssetDeliveryPreparationError, "approved version IDs"):
            AssetDeliveryPreparationWorker()(contract)

    def test_rejects_manifest_lineage_mismatch(self) -> None:
        contract = _contract()
        contract["reviewed_assets"][0]["production_job_id"] = "wrong-job"
        with self.assertRaisesRegex(AssetDeliveryPreparationError, "lineage"):
            AssetDeliveryPreparationWorker()(contract)


if __name__ == "__main__":
    unittest.main()
