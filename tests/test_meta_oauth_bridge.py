from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.inbound_leads import FileInboundLeadStore
from runtime.meta_oauth import MetaOAuthError, MetaOAuthResult


class MetaOAuthBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = mock.Mock()
        base.bridge_token = "bridge-secret"
        self.oauth = mock.Mock()
        self.app = LeadAwareTonyApplication(
            base,
            FileInboundLeadStore(Path(self.temporary.name) / "leads.json"),
            meta_oauth=self.oauth,
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
        status, payload = self.call("/oauth/meta/start", {}, token="")
        self.assertTrue(status.startswith("401"))
        self.assertFalse(payload["ok"])

    def test_start_returns_only_safe_read_only_configuration(self):
        self.oauth.authorization_url.return_value = "https://www.facebook.com/v26.0/dialog/oauth?state=random"
        status, payload = self.call("/oauth/meta/start", {})
        self.assertTrue(status.startswith("200"))
        self.assertTrue(payload["read_only"])
        self.assertNotIn("app_secret", json.dumps(payload))
        self.assertNotIn("access_token", json.dumps(payload))

    def test_callback_does_not_echo_code_state_or_token(self):
        self.oauth.exchange.return_value = MetaOAuthResult(
            ("123",),
            ("ads_management", "ads_read"),
            ("manage_ads", "manage_campaigns", "read_ads"),
        )
        status, payload = self.call("/oauth/meta/callback", {"state": "state-secret", "code": "code-secret"})
        rendered = json.dumps(payload)
        self.assertTrue(status.startswith("200"))
        self.assertNotIn("state-secret", rendered)
        self.assertNotIn("code-secret", rendered)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["runtime_mutation_authority"])
        self.assertIn("manage_campaigns", payload["provider_capabilities"])

    def test_callback_returns_sanitised_fail_closed_error(self):
        self.oauth.exchange.side_effect = MetaOAuthError("Meta credential verification failed")
        status, payload = self.call("/oauth/meta/callback", {"state": "state-secret", "code": "code-secret"})
        rendered = json.dumps(payload)
        self.assertTrue(status.startswith("400"))
        self.assertNotIn("state-secret", rendered)
        self.assertNotIn("code-secret", rendered)


if __name__ == "__main__":
    unittest.main()
