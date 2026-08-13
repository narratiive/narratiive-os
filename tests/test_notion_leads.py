from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from runtime.inbound_leads import FileInboundLeadStore
from runtime.notion_leads import (
    NotionLeadConfig,
    NotionLeadSource,
    NotionLeadSourceError,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class NotionLeadSourceTests(unittest.TestCase):
    def test_config_requires_notion_token(self):
        with self.assertRaises(NotionLeadSourceError):
            NotionLeadConfig.from_env({})

    def test_config_accepts_canonical_token_name(self):
        config = NotionLeadConfig.from_env({"NARRATIIVE_NOTION_TOKEN": "secret"})
        self.assertEqual(config.token, "secret")
        self.assertEqual(config.notion_version, "2026-03-11")

    def test_reads_notion_as_authoritative_source_and_refreshes_cache(self):
        payload = {
            "object": "list",
            "has_more": False,
            "next_cursor": None,
            "results": [
                {
                    "id": "page-1",
                    "created_time": "2026-08-13T10:39:17.000Z",
                    "url": "https://notion.so/page-1",
                    "properties": {
                        "Contact": {"title": [{"plain_text": "Lesley Harman"}]},
                        "Company": {"rich_text": [{"plain_text": "Harman Communications Ltd"}]},
                        "Email": {"email": "lesley@harman.com"},
                        "Source": {"select": {"name": "Tally"}},
                        "Status": {"status": {"name": "New"}},
                        "Pipeline Stage": {"select": {"name": "New Diagnostic"}},
                        "Lead Temperature": {"select": {"name": "Warm"}},
                        "AI Summary": {"rich_text": [{"plain_text": "Tally inbound enquiry."}]},
                        "Recommended Next Action": {
                            "rich_text": [{"plain_text": "Review the inbound lead."}]
                        },
                    },
                }
            ],
        }
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers.get("Authorization")
            captured["version"] = request.headers.get("Notion-version")
            return FakeResponse(payload)

        with tempfile.TemporaryDirectory() as tmp:
            cache = FileInboundLeadStore(Path(tmp) / "leads.json")
            source = NotionLeadSource(
                NotionLeadConfig(token="secret"),
                cache=cache,
                opener=opener,
            )
            leads = source.read()
            cached = cache.read()

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].contact, "Lesley Harman")
        self.assertEqual(leads[0].company, "Harman Communications Ltd")
        self.assertEqual(leads[0].lead_temperature, "Warm")
        self.assertEqual(leads[0].created_at, "2026-08-13T10:39:17.000Z")
        self.assertEqual(cached[0].lead_id, "page-1")
        self.assertIn("/v1/data_sources/34b0c9cf-a8f2-80af-98e4-000b95243de6/query", captured["url"])
        self.assertEqual(captured["authorization"], "Bearer secret")
        self.assertEqual(captured["version"], "2026-03-11")

    def test_api_failure_raises_instead_of_claiming_empty_leads(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"message":"bad token"}'))

        source = NotionLeadSource(NotionLeadConfig(token="bad"), opener=opener)
        with self.assertRaises(NotionLeadSourceError):
            source.read()


if __name__ == "__main__":
    unittest.main()
