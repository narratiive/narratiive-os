from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.inbound_leads import FileInboundLeadStore


class TonyLeadIngestAuthTests(unittest.TestCase):
    def _app(self, root: str) -> tuple[LeadAwareTonyApplication, FileInboundLeadStore]:
        base = mock.Mock()
        base.bridge_token = "bridge-secret"
        store = FileInboundLeadStore(Path(root) / "leads.json")
        app = LeadAwareTonyApplication(base, store, agent_gateway=mock.Mock())
        return app, store

    @staticmethod
    def _environ(*, authorization: str = "") -> dict:
        payload = json.dumps(
            {
                "lead_id": "lead-auth-1",
                "contact": "Auth Test",
                "company": "Example Co",
                "source": "Growth Diagnostic",
                "status": "New",
            }
        ).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/leads/ingest",
            "REMOTE_ADDR": "127.0.0.1",
            "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(payload),
        }
        if authorization:
            environ["HTTP_AUTHORIZATION"] = authorization
        return environ

    @staticmethod
    def _call(app: LeadAwareTonyApplication, environ: dict) -> tuple[str, dict]:
        observed: dict[str, object] = {}
        response = app(
            environ,
            lambda status, headers: observed.update(status=status, headers=headers),
        )
        return str(observed["status"]), json.loads(b"".join(response))

    def test_loopback_without_authorization_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, store = self._app(tmp)
            status, payload = self._call(app, self._environ())
            self.assertTrue(status.startswith("401"))
            self.assertEqual(payload["error"]["code"], "unauthorized")
            self.assertEqual(store.read(), ())

    def test_loopback_with_wrong_authorization_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, store = self._app(tmp)
            status, payload = self._call(app, self._environ(authorization="Bearer wrong-secret"))
            self.assertTrue(status.startswith("401"))
            self.assertEqual(payload["error"]["code"], "unauthorized")
            self.assertEqual(store.read(), ())

    def test_loopback_with_exact_bridge_token_is_ingested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, store = self._app(tmp)
            status, payload = self._call(app, self._environ(authorization="Bearer bridge-secret"))
            self.assertTrue(status.startswith("200"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "lead_ingested")
            self.assertEqual(len(store.read()), 1)
            self.assertEqual(store.read()[0].lead_id, "lead-auth-1")


if __name__ == "__main__":
    unittest.main()
