from __future__ import annotations

import unittest

from runtime.client_asset_delivery_adapter import ClientAssetDeliveryAdapter, ClientAssetDeliveryError


def _contract() -> dict:
    checksum = "a" * 64
    assets = [{"asset_version_id": "safe-asset-v1"}, {"asset_version_id": "safe-asset-v2"}]
    return {
        "workflow_context": {"workflow_id": "asset_review_to_delivery_preparation"},
        "delivery_package": {
            "delivery_package_id": "safe-package",
            "checksum": checksum,
            "assets": assets,
        },
        "delivery_manifest": {"delivery_package_checksum": checksum, "assets": assets},
        "proposed_delivery_action": {
            "delivery_package_checksum": checksum,
            "destination": "safe client Drive folder",
            "requires_human_approval": True,
            "execution_authorised": False,
        },
    }


def _result(contract: dict) -> dict:
    package = contract["delivery_package"]
    checksum = package["checksum"]
    return {
        "verified_delivery_evidence": {
            "delivery_package_id": package["delivery_package_id"],
            "delivery_package_checksum": checksum,
            "destination": "safe client Drive folder",
            "delivered_at": "2026-09-19T12:00:00Z",
            "delivered_asset_version_ids": [item["asset_version_id"] for item in package["assets"]],
        },
        "delivery_receipt": {
            "receipt_id": "safe-receipt",
            "delivery_package_checksum": checksum,
            "status": "delivered",
        },
        "external_action_receipt": {"receipt_id": "safe-receipt"},
        "external_action_taken": True,
        "delivery_authorised": True,
        "publication_authorised": False,
        "media_spend_authorised": False,
    }


class ClientAssetDeliveryAdapterTests(unittest.TestCase):
    def test_accepts_exact_receipted_delivery_only(self) -> None:
        result = ClientAssetDeliveryAdapter(_result)(_contract())
        self.assertTrue(result["delivery_authorised"])
        self.assertFalse(result["publication_authorised"])

    def test_rejects_partial_delivery_evidence(self) -> None:
        def provider(contract):
            result = _result(contract)
            result["verified_delivery_evidence"]["delivered_asset_version_ids"].pop()
            return result

        with self.assertRaisesRegex(ClientAssetDeliveryError, "exact approved package"):
            ClientAssetDeliveryAdapter(provider)(_contract())

    def test_rejects_stale_package_binding(self) -> None:
        contract = _contract()
        contract["proposed_delivery_action"]["delivery_package_checksum"] = "0" * 64
        with self.assertRaisesRegex(ClientAssetDeliveryError, "stale"):
            ClientAssetDeliveryAdapter(_result)(contract)

    def test_rejects_publication_or_spend_authority(self) -> None:
        def provider(contract):
            result = _result(contract)
            result["publication_authorised"] = True
            return result

        with self.assertRaisesRegex(ClientAssetDeliveryError, "publication_authorised"):
            ClientAssetDeliveryAdapter(provider)(_contract())


if __name__ == "__main__":
    unittest.main()
