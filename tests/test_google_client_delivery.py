from __future__ import annotations

import unittest
from datetime import datetime, timezone

from runtime.google_client_delivery import (
    GoogleClientDeliveryDispatcher,
    GoogleClientDeliveryError,
)


def _contract() -> dict:
    checksum = "a" * 64
    return {
        "workflow_context": {"workflow_id": "asset_review_to_delivery_preparation"},
        "delivery_package": {
            "delivery_package_id": "safe-package",
            "checksum": checksum,
            "campaign_identity": {"campaign_name": "SAFE Synthetic Campaign"},
            "delivery_requirements": {
                "client_drive_folder_id": "safe-client-folder",
                "notification_email": "client@example.invalid",
            },
            "assets": [
                {
                    "asset_version_id": "safe-asset-v1",
                    "file_checksum": "b" * 64,
                    "drive_uri": "https://drive.google.com/file/d/safe-source-file/view",
                }
            ],
        },
    }


class GoogleClientDeliveryTests(unittest.TestCase):
    def test_copies_exact_assets_then_sends_notification(self) -> None:
        events = []

        def drive(contract):
            events.append(("drive", contract))
            return {
                "verified": True,
                "file_id": "safe-copy-file",
                "file_url": "https://drive.google.com/file/d/safe-copy-file/view",
            }

        def gmail(contract):
            events.append(("gmail", contract))
            return {"verified": True, "sent": True, "message_id": "safe-message"}

        dispatcher = GoogleClientDeliveryDispatcher(
            drive_dispatcher=drive,
            gmail_dispatcher=gmail,
            clock=lambda: datetime(2026, 9, 19, 12, tzinfo=timezone.utc),
        )

        result = dispatcher(_contract())

        self.assertEqual([item[0] for item in events], ["drive", "gmail"])
        self.assertEqual(events[0][1]["payload"]["source_file_id"], "safe-source-file")
        self.assertEqual(events[0][1]["payload"]["destination_folder_id"], "safe-client-folder")
        self.assertEqual(events[1][1]["payload"]["recipient_email"], "client@example.invalid")
        self.assertIn("safe-copy-file", events[1][1]["payload"]["body"])
        self.assertEqual(
            result["verified_delivery_evidence"]["delivered_asset_version_ids"],
            ["safe-asset-v1"],
        )
        self.assertEqual(result["delivery_receipt"]["gmail_message_id"], "safe-message")
        self.assertTrue(result["delivery_authorised"])
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])

    def test_does_not_email_until_all_drive_copies_are_verified(self) -> None:
        gmail_calls = []
        dispatcher = GoogleClientDeliveryDispatcher(
            drive_dispatcher=lambda _contract: {"verified": False},
            gmail_dispatcher=lambda contract: gmail_calls.append(contract) or {},
        )

        with self.assertRaisesRegex(GoogleClientDeliveryError, "did not verify"):
            dispatcher(_contract())

        self.assertEqual(gmail_calls, [])

    def test_requires_explicit_per_client_destination(self) -> None:
        contract = _contract()
        contract["delivery_package"]["delivery_requirements"] = {}
        dispatcher = GoogleClientDeliveryDispatcher(
            drive_dispatcher=lambda _contract: {},
            gmail_dispatcher=lambda _contract: {},
        )

        with self.assertRaisesRegex(GoogleClientDeliveryError, "folder ID"):
            dispatcher(contract)


if __name__ == "__main__":
    unittest.main()
