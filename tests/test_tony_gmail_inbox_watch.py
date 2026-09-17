from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.tony_gmail_inbox_watch import GmailInboxWatchService


class GmailInboxWatchTests(unittest.TestCase):
    def test_alerts_new_person_to_person_mail_and_deduplicates(self):
        sent: list[str] = []

        def gmail(_contract):
            return {
                "verified": True,
                "read_only": True,
                "mutation_count": 0,
                "source_id": "gmail:search",
                "results": [
                    {
                        "message_id": "person-1",
                        "from": "Mariah <mariah@example.invalid>",
                        "subject": "Re: New conversation",
                        "snippet": "Happy to arrange a conversation.",
                        "label_ids": ["INBOX", "UNREAD"],
                    },
                    {
                        "message_id": "bulk-1",
                        "from": "News <news@example.invalid>",
                        "subject": "Weekly newsletter",
                        "snippet": "Products and events",
                        "label_ids": ["INBOX", "UNREAD"],
                        "list_unsubscribe": True,
                    },
                    {
                        "message_id": "self-1",
                        "from": "Matt <hello@narratiive.com>",
                        "subject": "Internal review",
                        "label_ids": ["INBOX"],
                    },
                ],
            }

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            service = GmailInboxWatchService(gmail, state, sent.append)
            first = service.run()
            second = service.run()
            last_successful_check_at = json.loads(state.read_text())["last_successful_check_at"]

        self.assertEqual(first.status, "attention_sent")
        self.assertEqual(first.alerted, 1)
        self.assertEqual(first.candidates, 1)
        self.assertEqual(first.message_ids, ("person-1",))
        self.assertIn("Mariah", sent[0])
        self.assertIn("I have not replied", sent[0])
        self.assertEqual(second.status, "no_new_actionable_mail")
        self.assertEqual(len(sent), 1)
        self.assertTrue(last_successful_check_at)

    def test_unverified_gmail_result_never_sends_or_advances_state(self):
        sent: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            service = GmailInboxWatchService(lambda _contract: {}, state, sent.append)
            result = service.run()
            self.assertEqual(result.status, "unverified_read")
            self.assertFalse(state.exists())
        self.assertEqual(sent, [])

    def test_delivery_failure_leaves_message_unseen_for_retry(self):
        evidence = {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "results": [{
                "message_id": "person-1",
                "from": "Friend <friend@example.invalid>",
                "subject": "Introduction",
                "snippet": "A colleague may need your help.",
                "label_ids": ["INBOX"],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            service = GmailInboxWatchService(
                lambda _contract: evidence,
                state,
                lambda _message: (_ for _ in ()).throw(RuntimeError("offline")),
            )
            with self.assertRaisesRegex(RuntimeError, "offline"):
                service.run()
            self.assertFalse(state.exists())

    def test_ingests_actionable_mail_once_and_retries_failed_ingestion(self):
        evidence = {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "results": [{
                "message_id": "person-1",
                "from": "Friend <friend@example.invalid>",
                "subject": "Introduction",
                "snippet": "A colleague may need your help.",
                "label_ids": ["INBOX"],
            }],
        }
        attempts: list[str] = []

        def ingest(item):
            attempts.append(item["message_id"])
            return len(attempts) > 1

        with tempfile.TemporaryDirectory() as directory:
            service = GmailInboxWatchService(
                lambda _contract: evidence,
                Path(directory) / "state.json",
                lambda _message: None,
                ingest_lead_candidate=ingest,
            )
            failed = service.run()
            succeeded = service.run()
            replay = service.run()

        self.assertEqual(failed.ingest_failed, 1)
        self.assertEqual(failed.candidates, 1)
        self.assertEqual(failed.ingested, 0)
        self.assertEqual(succeeded.ingested, 1)
        self.assertEqual(succeeded.ingest_failed, 0)
        self.assertEqual(replay.alerted, 0)
        self.assertEqual(attempts, ["person-1", "person-1"])


if __name__ == "__main__":
    unittest.main()
