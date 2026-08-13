from __future__ import annotations

import io
import json
import unittest

from openclaw.tony_live_bridge import LeadAwareTonyApplication


class FakeBase:
    bridge_token = "secret"

    def __call__(self, environ, start_response):
        raise AssertionError("base should not receive /leads/ingest")


class RecordingStore:
    def __init__(self) -> None:
        self.leads = []

    def upsert(self, lead) -> None:
        self.leads.append(lead)


def call_ingest(app: LeadAwareTonyApplication, *, remote_addr: str, authorization: str = ""):
    body = json.dumps(
        {
            "id": "notion-page-1",
            "url": "https://notion.so/notion-page-1",
            "properties": {
                "Contact": {"title": [{"plain_text": "Lesley Harman"}]},
                "Company": {"rich_text": [{"plain_text": "Harman Communications Ltd"}]},
                "Email": {"email": "lesley@harman.com"},
                "Source": {"select": {"name": "Tally"}},
                "Status": {"status": {"name": "New"}},
                "Pipeline Stage": {"select": {"name": "New Diagnostic"}},
                "Lead Temperature": {"select": {"name": "Warm"}},
                "Recommended Next Action": {
                    "rich_text": [{"plain_text": "Review the inbound lead."}]
                },
            },
        }
    ).encode("utf-8")
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/leads/ingest",
        "REMOTE_ADDR": remote_addr,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": io.BytesIO(body),
    }
    if authorization:
        environ["HTTP_AUTHORIZATION"] = authorization
    captured = {}

    def start_response(status, headers):
        captured["status"] = status

    response = b"".join(app(environ, start_response))
    return captured["status"], json.loads(response.decode("utf-8"))


class LocalLeadSyncAuthTests(unittest.TestCase):
    def test_loopback_n8n_can_ingest_without_bridge_secret(self):
        store = RecordingStore()
        app = LeadAwareTonyApplication(FakeBase(), store)
        status, payload = call_ingest(app, remote_addr="127.0.0.1")
        self.assertEqual(status, "200 OK")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["contact"], "Lesley Harman")
        self.assertEqual(len(store.leads), 1)

    def test_non_local_ingest_still_requires_bridge_secret(self):
        store = RecordingStore()
        app = LeadAwareTonyApplication(FakeBase(), store)
        status, payload = call_ingest(app, remote_addr="10.0.0.12")
        self.assertEqual(status, "401 Unauthorized")
        self.assertFalse(payload["ok"])
        self.assertEqual(store.leads, [])

    def test_non_local_ingest_accepts_valid_bridge_secret(self):
        store = RecordingStore()
        app = LeadAwareTonyApplication(FakeBase(), store)
        status, payload = call_ingest(
            app,
            remote_addr="10.0.0.12",
            authorization="Bearer secret",
        )
        self.assertEqual(status, "200 OK")
        self.assertTrue(payload["ok"])
        self.assertEqual(len(store.leads), 1)


if __name__ == "__main__":
    unittest.main()
