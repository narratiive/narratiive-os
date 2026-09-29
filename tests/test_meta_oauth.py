from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from runtime.media_provider_transports import JSONResponse
from runtime.meta_oauth import (
    META_REDIRECT_URI,
    MetaOAuthError,
    MetaOAuthService,
    MetaOAuthStateError,
    MetaOAuthStateStore,
)
from runtime.tiktok_oauth import ProtectedRuntimeEnvironment


class FakeHTTP:
    def __init__(self, responses=()) -> None:
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers=None, query=None, body=None, form=None):
        self.calls.append({"method": method, "url": url, "query": dict(query or {})})
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class MetaOAuthTests(unittest.TestCase):
    def service(self, directory: str, http: FakeHTTP) -> MetaOAuthService:
        return MetaOAuthService(
            app_id="app-id",
            app_secret="app-secret",
            graph_version="v26.0",
            state_store=MetaOAuthStateStore(Path(directory) / "state.json"),
            environment=ProtectedRuntimeEnvironment(Path(directory) / "runtime.env"),
            http=http,
        )

    def test_authorization_url_uses_exact_redirect_state_and_read_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, FakeHTTP())
            url = service.authorization_url()
            parsed = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qs(parsed.query)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.hostname, "www.facebook.com")
            self.assertEqual(query["redirect_uri"], [META_REDIRECT_URI])
            self.assertEqual(set(query["scope"][0].split(",")), {"ads_read"})
            self.assertNotIn("ads_management", query["scope"][0])
            state_file = Path(directory) / "state.json"
            stored = state_file.read_text(encoding="utf-8")
            self.assertNotIn(query["state"][0], stored)
            self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

    def test_exchange_validates_scopes_and_stores_single_account_securely(self):
        with tempfile.TemporaryDirectory() as directory:
            http = FakeHTTP(
                (
                    JSONResponse(200, {}, {"access_token": "short-token"}),
                    JSONResponse(200, {}, {"access_token": "long-token"}),
                    JSONResponse(200, {}, {"data": [
                        {"permission": "ads_read", "status": "granted"},
                        {"permission": "public_profile", "status": "granted"},
                    ]}),
                    JSONResponse(200, {}, {"data": [{
                        "id": "act_123", "account_id": "123", "currency": "GBP", "timezone_name": "Europe/London"
                    }]}),
                )
            )
            service = self.service(directory, http)
            url = service.authorization_url()
            state = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["state"][0]
            result = service.exchange(state=state, code="one-time-code")
            self.assertEqual(result.account_ids, ("123",))
            content = (Path(directory) / "runtime.env").read_text(encoding="utf-8")
            self.assertIn("META_ACCESS_TOKEN=long-token", content)
            self.assertIn("META_ACCOUNT_ID=123", content)
            self.assertIn("META_TIMEZONE=Europe/London", content)
            self.assertIn("META_CURRENCY=GBP", content)
            self.assertNotIn("short-token", content)
            self.assertEqual((Path(directory) / "runtime.env").stat().st_mode & 0o777, 0o600)
            self.assertTrue(http.calls[2]["query"]["appsecret_proof"])

    def test_state_is_single_use_even_when_exchange_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, FakeHTTP((JSONResponse(400, {}, {"error": {}}),)))
            state = urllib.parse.parse_qs(urllib.parse.urlsplit(service.authorization_url()).query)["state"][0]
            with self.assertRaises(MetaOAuthError):
                service.exchange(state=state, code="bad-code")
            with self.assertRaises(MetaOAuthStateError):
                service.exchange(state=state, code="bad-code")

    def test_exchange_paginates_accounts_by_cursor_without_following_next_url(self):
        with tempfile.TemporaryDirectory() as directory:
            http = FakeHTTP(
                (
                    JSONResponse(200, {}, {"access_token": "short-token"}),
                    JSONResponse(200, {}, {"access_token": "long-token"}),
                    JSONResponse(200, {}, {"data": [{"permission": "ads_read", "status": "granted"}]}),
                    JSONResponse(200, {}, {
                        "data": [{"id": "act_123", "account_id": "123"}],
                        "paging": {"cursors": {"after": "safe-cursor"}, "next": "https://attacker.invalid"},
                    }),
                    JSONResponse(200, {}, {"data": [{"id": "act_456", "account_id": "456"}]}),
                )
            )
            service = self.service(directory, http)
            state = urllib.parse.parse_qs(
                urllib.parse.urlsplit(service.authorization_url()).query
            )["state"][0]
            result = service.exchange(state=state, code="one-time-code")
            self.assertEqual(result.account_ids, ("123", "456"))
            self.assertEqual(http.calls[4]["url"], "https://graph.facebook.com/v26.0/me/adaccounts")
            self.assertEqual(http.calls[4]["query"]["after"], "safe-cursor")
            self.assertNotIn("META_ACCOUNT_ID", (Path(directory) / "runtime.env").read_text())

    def test_forbidden_write_scope_fails_closed_without_storing_token(self):
        with tempfile.TemporaryDirectory() as directory:
            http = FakeHTTP(
                (
                    JSONResponse(200, {}, {"access_token": "short-token"}),
                    JSONResponse(200, {}, {"access_token": "long-token"}),
                    JSONResponse(200, {}, {"data": [
                        {"permission": "ads_read", "status": "granted"},
                        {"permission": "ads_management", "status": "granted"},
                    ]}),
                )
            )
            service = self.service(directory, http)
            state = urllib.parse.parse_qs(urllib.parse.urlsplit(service.authorization_url()).query)["state"][0]
            with self.assertRaisesRegex(MetaOAuthError, "prohibited"):
                service.exchange(state=state, code="code")
            self.assertFalse((Path(directory) / "runtime.env").exists())


if __name__ == "__main__":
    unittest.main()
