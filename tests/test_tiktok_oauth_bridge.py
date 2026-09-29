from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.inbound_leads import FileInboundLeadStore
from runtime.tiktok_oauth import TikTokOAuthError, TikTokOAuthResult


class TikTokOAuthBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = mock.Mock()
        base.bridge_token = "bridge-secret"
        self.oauth = mock.Mock()
        self.app = LeadAwareTonyApplication(
            base,
            FileInboundLeadStore(Path(self.temporary.name) / "leads.json"),
            tiktok_oauth=self.oauth,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, path, payload, token="Bearer bridge-secret"):
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(raw)),
            "HTTP_AUTHORIZATION": token,
            "wsgi.input": io.BytesIO(raw),
        }
        status = {}
        response = self.app(environ, lambda value, headers: status.update(value=value))
        return status["value"], json.loads(b"".join(response))

    def test_start_requires_bridge_authentication(self):
        status, payload = self.call("/oauth/tiktok/start", {}, token="")
        self.assertTrue(status.startswith("401"))
        self.assertFalse(payload["ok"])

    def test_start_returns_only_safe_configuration(self):
        self.oauth.authorization_url.return_value = "https://business-api.tiktok.com/auth?state=random"
        status, payload = self.call("/oauth/tiktok/start", {})
        self.assertTrue(status.startswith("200"))
        self.assertTrue(payload["read_only"])
        self.assertNotIn("access_token", json.dumps(payload))
        self.assertNotIn("app_secret", json.dumps(payload))

    def test_callback_does_not_echo_code_state_or_token(self):
        self.oauth.exchange.return_value = TikTokOAuthResult(
            ("123",),
            ("44", "100", "200", "201", "210", "211", "220", "221"),
            ("manage_ads", "manage_ad_groups", "manage_campaigns"),
        )
        status, payload = self.call("/oauth/tiktok/callback", {"state": "state-secret", "auth_code": "code-secret", "provider_code": "0"})
        rendered = json.dumps(payload)
        self.assertTrue(status.startswith("200"))
        self.assertNotIn("state-secret", rendered)
        self.assertNotIn("code-secret", rendered)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["runtime_mutation_authority"])
        self.assertIn("manage_campaigns", payload["provider_capabilities"])

    def test_callback_returns_sanitised_fail_closed_error(self):
        self.oauth.exchange.side_effect = TikTokOAuthError("TikTok rejected the authorisation-code exchange")
        status, payload = self.call("/oauth/tiktok/callback", {"state": "state-secret", "auth_code": "code-secret"})
        rendered = json.dumps(payload)
        self.assertTrue(status.startswith("400"))
        self.assertNotIn("state-secret", rendered)
        self.assertNotIn("code-secret", rendered)


if __name__ == "__main__":
    unittest.main()
