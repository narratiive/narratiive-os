from __future__ import annotations

import hashlib
import json
import unittest

from runtime.creative_production_workflow_adapter import (
    CreativeProductionWorkflowAdapter,
    CreativeProductionWorkflowError,
)


def _contract() -> dict:
    return {
        "workflow_context": {"workflow_id": "creative_bible_to_asset_production"},
        "asset_manifest": {
            "manifest_id": "safe-manifest",
            "assets": [
                {"asset_id": "safe-asset-1", "production_job_id": "safe-job-1"},
                {"asset_id": "safe-asset-2", "production_job_id": "safe-job-2"},
            ],
        },
        "production_tasks": [
            {"asset_id": "safe-asset-1", "production_job_id": "safe-job-1"},
            {"asset_id": "safe-asset-2", "production_job_id": "safe-job-2"},
        ],
    }


def _provider_result(contract: dict) -> dict:
    manifest_checksum = hashlib.sha256(
        json.dumps(contract["asset_manifest"], sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    versions = [
        {
            "asset_version_id": f"{item['asset_id']}-v1",
            "asset_id": item["asset_id"],
            "production_job_id": item["production_job_id"],
            "file_checksum": hashlib.sha256(item["asset_id"].encode("utf-8")).hexdigest(),
            "drive_uri": f"https://drive.google.invalid/{item['asset_id']}-v1",
            "source_manifest_checksum": manifest_checksum,
            "version_number": 1,
            "status": "generated",
            "approval_status": "pending",
            "human_review_required": True,
            "delivery_authorised": False,
            "publication_authorised": False,
        }
        for item in contract["asset_manifest"]["assets"]
    ]
    return {
        "asset_versions": versions,
        "production_receipts": [
            {
                "asset_version_id": item["asset_version_id"],
                "provider_receipt_id": f"receipt-{item['asset_version_id']}",
                "status": "complete",
            }
            for item in versions
        ],
        "external_action_taken": True,
        "external_action_receipt": {"provider_batch_id": "safe-batch"},
        "delivery_authorised": False,
        "publication_authorised": False,
        "media_spend_authorised": False,
    }


class CreativeProductionWorkflowAdapterTests(unittest.TestCase):
    def test_accepts_complete_checksum_bound_provider_output(self) -> None:
        result = CreativeProductionWorkflowAdapter(_provider_result)(_contract())
        self.assertEqual(len(result["asset_versions"]), 2)
        self.assertFalse(result["publication_authorised"])

    def test_rejects_missing_manifest_asset(self) -> None:
        def provider(contract):
            result = _provider_result(contract)
            result["asset_versions"].pop()
            result["production_receipts"].pop()
            return result

        with self.assertRaisesRegex(CreativeProductionWorkflowError, "exact Asset Manifest"):
            CreativeProductionWorkflowAdapter(provider)(_contract())

    def test_rejects_wrong_manifest_checksum(self) -> None:
        def provider(contract):
            result = _provider_result(contract)
            result["asset_versions"][0]["source_manifest_checksum"] = "0" * 64
            return result

        with self.assertRaisesRegex(CreativeProductionWorkflowError, "checksum"):
            CreativeProductionWorkflowAdapter(provider)(_contract())

    def test_rejects_any_publication_authority_claim(self) -> None:
        def provider(contract):
            result = _provider_result(contract)
            result["publication_authorised"] = True
            return result

        with self.assertRaisesRegex(CreativeProductionWorkflowError, "publication_authorised"):
            CreativeProductionWorkflowAdapter(provider)(_contract())


if __name__ == "__main__":
    unittest.main()
