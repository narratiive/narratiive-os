from __future__ import annotations

import json
import unittest
from unittest import mock

from scripts.run_gmail_inbox_watch import ingest_email_candidate


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return b'{"ok":true}'


class RunGmailInboxWatchTests(unittest.TestCase):
    def test_email_candidate_uses_message_id_and_never_requests_a_reply(self):
        captured = None

        def open_request(call, timeout):
            nonlocal captured
            captured = json.loads(call.data.decode("utf-8"))
            self.assertEqual(timeout, 30)
            return _Response()

        with mock.patch("scripts.run_gmail_inbox_watch.request.urlopen", side_effect=open_request):
            result = ingest_email_candidate(
                {
                    "message_id": "msg-1",
                    "thread_id": "thread-1",
                    "from": "Mariah Wilson <mariah@example.invalid>",
                    "subject": "Introduction",
                    "snippet": "A colleague suggested I contact you.",
                    "date": "Thu, 17 Sep 2026 09:00:00 +0100",
                },
                "http://127.0.0.1:5678/webhook/diagnostic-lead",
            )

        self.assertTrue(result)
        self.assertEqual(captured["lead_id"], "gmail:msg-1")
        self.assertEqual(captured["source"], "Email")
        self.assertEqual(captured["email"], "mariah@example.invalid")
        self.assertNotIn("reply", captured)


if __name__ == "__main__":
    unittest.main()
