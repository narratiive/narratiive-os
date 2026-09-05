from __future__ import annotations

import json
import unittest
from unittest import mock

from runtime.tony_dispatch_adapters import build_http_dispatchers


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TonyDispatchAdapterTests(unittest.TestCase):
    def test_explicit_empty_environment_does_not_inherit_process_credentials(self):
        with mock.patch.dict(
            "os.environ",
            {"TONY_DISPATCH_GMAIL_URL": "http://127.0.0.1:9001/gmail"},
            clear=True,
        ):
            self.assertEqual(build_http_dispatchers({}), {})

    def test_only_explicitly_configured_workers_are_enabled(self):
        dispatchers = build_http_dispatchers(
            {
                "TONY_DISPATCH_GMAIL_URL": "http://127.0.0.1:9001/gmail",
                "TONY_DISPATCH_GITHUB_URL": "http://127.0.0.1:9002/github",
            }
        )

        self.assertEqual(set(dispatchers), {"Gmail", "GitHub"})

    def test_handler_posts_contract_and_returns_nested_evidence(self):
        dispatchers = build_http_dispatchers(
            {
                "TONY_DISPATCH_GMAIL_URL": "http://127.0.0.1:9001/gmail",
                "TONY_DISPATCH_GMAIL_TOKEN": "secret",
            }
        )

        with mock.patch(
            "runtime.tony_dispatch_adapters.request.urlopen",
            return_value=_Response({"evidence": {"thread_id": "t-1", "read_only": True}}),
        ) as opened:
            evidence = dispatchers["Gmail"]({"instruction": "read thread", "target": {"lead_id": "l1"}})

        self.assertEqual(evidence["thread_id"], "t-1")
        req = opened.call_args.args[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:9001/gmail")
        self.assertEqual(req.get_header("Authorization"), "Bearer secret")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["dispatch"]["instruction"], "read thread")

    def test_handler_rejects_empty_or_non_object_evidence(self):
        dispatchers = build_http_dispatchers(
            {"TONY_DISPATCH_CLAUDE_URL": "http://127.0.0.1:9003/claude"}
        )

        with mock.patch(
            "runtime.tony_dispatch_adapters.request.urlopen",
            return_value=_Response({}),
        ):
            with self.assertRaisesRegex(RuntimeError, "no structured evidence"):
                dispatchers["Claude"]({"instruction": "draft"})


if __name__ == "__main__":
    unittest.main()
