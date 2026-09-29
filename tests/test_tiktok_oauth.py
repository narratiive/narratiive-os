from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from runtime.media_provider_transports import JSONResponse
from runtime.tiktok_oauth import (
    ProtectedRuntimeEnvironment,
    TIKTOK_REDIRECT_URI,
    TIKTOK_REQUIRED_SCOPES,
    TikTokOAuthError,
    TikTokOAuthService,
    TikTokOAuthStateError,
    TikTokOAuthStateStore,
)


class FakeHTTP:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return JSONResponse(self.status, {}, self.payload)


class TikTokOAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = TikTokOAuthStateStore(self.root / "state.json")
        self.environment = ProtectedRuntimeEnvironment(self.root / "runtime.env")

    def tearDown(self):
        self.temporary.cleanup()

    def service(self, http=None):
        return TikTokOAuthService(
            app_id="app-id",
            app_secret="app-secret",
            advertiser_authorization_url="https://business-api.tiktok.com/portal/auth?app_id=app-id",
            state_store=self.state,
            environment=self.environment,
            http=http,
        )

    def test_authorization_url_issues_hashed_one_time_state(self):
        url = self.service().authorization_url()
        issued = parse_qs(urlsplit(url).query)["state"][0]
        stored = (self.root / "state.json").read_text(encoding="utf-8")
        self.assertNotIn(issued, stored)
        self.assertEqual(stat.S_IMODE((self.root / "state.json").stat().st_mode), 0o600)
        self.state.consume(issued)
        with self.assertRaises(TikTokOAuthStateError):
            self.state.consume(issued)

    def test_mismatched_state_is_consumed_and_fails_closed(self):
        self.state.issue()
        with self.assertRaisesRegex(TikTokOAuthStateError, "does not match"):
            self.state.consume("wrong-state")
        self.assertFalse((self.root / "state.json").exists())

    def test_exchange_requires_exact_read_only_scopes_and_stores_securely(self):
        token = "sensitive-access-token"
        http = FakeHTTP({"code": 0, "data": {
            "access_token": token,
            "advertiser_ids": ["123456"],
            "scope": list(TIKTOK_REQUIRED_SCOPES),
        }})
        state = parse_qs(urlsplit(self.service(http).authorization_url()).query)["state"][0]
        result = self.service(http).exchange(state=state, auth_code="sensitive-auth-code")
        self.assertEqual(result.advertiser_ids, ("123456",))
        body = http.calls[0][2]["body"]
        self.assertEqual(body["auth_code"], "sensitive-auth-code")
        contents = (self.root / "runtime.env").read_text(encoding="utf-8")
        self.assertIn("TIKTOK_ACCESS_TOKEN=" + token, contents)
        self.assertIn("TIKTOK_ACCOUNT_ID=123456", contents)
        self.assertEqual(stat.S_IMODE((self.root / "runtime.env").stat().st_mode), 0o600)

    def test_extra_or_missing_scope_prevents_credential_write(self):
        for scopes in ({"100", "200"}, set(TIKTOK_REQUIRED_SCOPES) | {"201"}):
            with self.subTest(scopes=scopes):
                http = FakeHTTP({"code": 0, "data": {
                    "access_token": "must-not-be-written",
                    "advertiser_ids": ["123"],
                    "scope": list(scopes),
                }})
                state = parse_qs(urlsplit(self.service(http).authorization_url()).query)["state"][0]
                with self.assertRaisesRegex(TikTokOAuthError, "exactly"):
                    self.service(http).exchange(state=state, auth_code="auth-code")
                self.assertFalse((self.root / "runtime.env").exists())

    def test_provider_failure_is_sanitised(self):
        http = FakeHTTP({"code": 40001, "message": "leaked-code-sensitive-auth-code"})
        state = parse_qs(urlsplit(self.service(http).authorization_url()).query)["state"][0]
        with self.assertRaises(TikTokOAuthError) as raised:
            self.service(http).exchange(state=state, auth_code="sensitive-auth-code")
        self.assertNotIn("sensitive-auth-code", str(raised.exception))

    def test_runtime_update_preserves_unrelated_google_configuration(self):
        path = self.root / "runtime.env"
        path.write_text("GOOGLE_ADS_CUSTOMER_ID=9780735754\nTIKTOK_ACCESS_TOKEN=old\n", encoding="utf-8")
        self.environment.update({"TIKTOK_ACCESS_TOKEN": "new"})
        self.assertEqual(path.read_text(encoding="utf-8"), "GOOGLE_ADS_CUSTOMER_ID=9780735754\nTIKTOK_ACCESS_TOKEN=new\n")

    def test_symlink_environment_fails_closed(self):
        target = self.root / "target"
        target.write_text("", encoding="utf-8")
        link = self.root / "runtime.env"
        link.symlink_to(target)
        with self.assertRaisesRegex(TikTokOAuthError, "symbolic link"):
            self.environment.update({"TIKTOK_ACCESS_TOKEN": "token"})

    def test_redirect_uri_is_the_stable_https_callback(self):
        self.assertEqual(TIKTOK_REDIRECT_URI, "https://lushly-spoof-reheat.ngrok-free.dev/webhook/tiktok-media-oauth-callback")


if __name__ == "__main__":
    unittest.main()
