from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.execution_journal import ExecutionJournal
from runtime.media_control import (
    FixtureTransport,
    MediaControlService,
    MediaProvider,
    MetaReadOnlyAdapter,
    ProviderConfiguration,
)


ROOT = Path(__file__).resolve().parents[1]


class MediaSyncBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        configuration = ProviderConfiguration(
            provider=MediaProvider.META,
            account_id="test-meta-account",
            credential_env_names=("TEST_META_TOKEN",),
            timezone_name="Europe/London",
            currency="GBP",
        )
        self.transport = FixtureTransport(
            {
                "get_performance": json.loads(
                    (ROOT / "tests" / "fixtures" / "northstar_media" / "meta.json").read_text(encoding="utf-8")
                )
            }
        )
        adapter = MetaReadOnlyAdapter(
            configuration,
            self.transport,
            environment={"TEST_META_TOKEN": "fixture-only"},
        )
        self.service = MediaControlService(
            {MediaProvider.META: adapter},
            ExecutionJournal(self.temporary_directory.name),
        )
        self.base = mock.Mock()
        self.base.bridge_token = "bridge-secret"
        self.app = LeadAwareTonyApplication(
            self.base,
            mock.Mock(),
            agent_gateway=mock.Mock(),
            media_control=self.service,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def payload() -> dict:
        return {
            "request_id": "northstar-hourly-meta-20260917T1000Z",
            "tony_request": "Scheduled Northstar read-only performance sync",
            "identity": {
                "workspace_id": "test-northstar-workspace",
                "client_id": "northstar-test-co",
                "brand_id": "northstar-test-brand",
                "market_ids": ["gb"],
                "product_ids": ["northstar-test-product"],
                "campaign_id": "northstar-test-autumn-growth",
            },
            "provider_mapping": {
                "provider": "meta",
                "account_id": "test-meta-account",
                "campaign_id": "test-meta-campaign",
                "ad_group_ids": ["test-meta-group"],
                "ad_ids": ["test-meta-ad"],
                "creative_ids": ["test-meta-creative"],
            },
            "period_start": "2026-09-10T00:00:00Z",
            "period_end": "2026-09-17T00:00:00Z",
            "creative_mappings": [
                {
                    "narratiive_asset_id": "TEST-NORTHSTAR-CW01-VID-001",
                    "campaign_world_id": "test-northstar-cw-01",
                    "creative_territory": "Own the next horizon",
                    "format": "vertical_video",
                    "provider": "meta",
                    "placement": "reels",
                    "provider_creative_ids": ["test-meta-creative"],
                    "provider_ad_ids": ["test-meta-ad"],
                }
            ],
        }

    def call(self, payload: dict, *, token: str = "bridge-secret") -> tuple[str, dict]:
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/media/sync",
            "CONTENT_LENGTH": str(len(raw)),
            "CONTENT_TYPE": "application/json",
            "HTTP_AUTHORIZATION": f"Bearer {token}",
            "wsgi.input": io.BytesIO(raw),
        }
        response_status: dict[str, str] = {}
        response = self.app(
            environ,
            lambda status, _headers: response_status.update(status=status),
        )
        return response_status["status"], json.loads(b"".join(response))

    def test_sync_requires_bridge_authentication(self) -> None:
        status, body = self.call(self.payload(), token="wrong")
        self.assertTrue(status.startswith("401"))
        self.assertEqual(body["error"]["code"], "unauthorized")
        self.assertEqual(self.transport.calls, [])

    def test_sync_normalises_and_returns_only_non_executing_actions(self) -> None:
        status, body = self.call(self.payload())
        self.assertTrue(status.startswith("200"))
        self.assertEqual(body["snapshot"]["identity"]["client_id"], "northstar-test-co")
        self.assertEqual(body["snapshot"]["creative_mappings"][0]["narratiive_asset_id"], "TEST-NORTHSTAR-CW01-VID-001")
        self.assertTrue(body["recommendations"])
        self.assertFalse(body["external_action_taken"])
        self.assertFalse(body["publication_authorised"])
        self.assertFalse(body["media_spend_authorised"])
        self.assertEqual(len(self.transport.calls), 1)

    def test_duplicate_request_replays_audited_result_without_provider_read(self) -> None:
        first_status, first = self.call(self.payload())
        second_status, second = self.call(self.payload())
        self.assertTrue(first_status.startswith("200"))
        self.assertTrue(second_status.startswith("200"))
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(len(self.service.journal.read_all()), 1)

    def test_request_id_cannot_replay_another_clients_snapshot(self) -> None:
        first_status, _first = self.call(self.payload())
        conflicting = self.payload()
        conflicting["identity"]["client_id"] = "another-client"
        conflicting["identity"]["campaign_id"] = "another-campaign"
        second_status, second = self.call(conflicting)
        self.assertTrue(first_status.startswith("200"))
        self.assertTrue(second_status.startswith("400"))
        self.assertEqual(second["error"]["code"], "invalid_media_sync")
        self.assertIn("different payload", second["error"]["message"])
        self.assertEqual(len(self.transport.calls), 1)

    def test_malformed_request_fails_before_provider_read(self) -> None:
        payload = self.payload()
        payload["identity"]["market_ids"] = []
        status, body = self.call(payload)
        self.assertTrue(status.startswith("400"))
        self.assertEqual(body["error"]["code"], "invalid_media_sync")
        self.assertEqual(self.transport.calls, [])

    def test_invalid_period_fails_before_provider_read(self) -> None:
        payload = self.payload()
        payload["period_start"] = "not-a-date"
        status, body = self.call(payload)
        self.assertTrue(status.startswith("400"))
        self.assertEqual(body["error"]["code"], "invalid_media_sync")
        self.assertEqual(self.transport.calls, [])

    def test_cross_account_request_is_rejected_and_audited(self) -> None:
        payload = self.payload()
        payload["provider_mapping"]["account_id"] = "another-client-account"
        status, body = self.call(payload)
        self.assertTrue(status.startswith("503"))
        self.assertEqual(body["error"]["code"], "media_sync_unavailable")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.service.journal.read_all()[-1].status, "failed")

    def test_unconfigured_provider_fails_closed(self) -> None:
        payload = self.payload()
        payload["provider_mapping"]["provider"] = "google"
        payload["provider_mapping"]["account_id"] = "test-google-account"
        payload["creative_mappings"] = []
        status, body = self.call(payload)
        self.assertTrue(status.startswith("503"))
        self.assertEqual(body["error"]["code"], "media_sync_unavailable")
        self.assertEqual(self.transport.calls, [])


if __name__ == "__main__":
    unittest.main()
