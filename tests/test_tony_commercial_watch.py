from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_watch import TonyCommercialWatchCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    def execute(self, command, objects):
        self.calls.append(command)
        return self.response


class TonyCommercialWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name) / "commitments.json"

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def confirmation_response() -> CommandResponse:
        return CommandResponse(
            command="outreach_execution_confirmation",
            status="healthy",
            message="Confirmed end to end.",
            data={
                "lead": {
                    "lead_id": "lesley-1",
                    "contact": "Lesley Harman",
                    "company": "Harman Communications",
                    "email": "lesley@example.com",
                },
                "follow_up_commitment": {
                    "owner": "Tony",
                    "action": "Check for a reply from Lesley Harman and surface the opportunity if there is no response within 3 business days.",
                    "status": "pending",
                },
            },
        )

    def _seed_commitment(self) -> None:
        writer = TonyCommercialWatchCommandService(
            StubCommandService(self.confirmation_response()),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 14, 10, 0),
        )
        writer.execute("Execution confirmed", [])

    def test_confirmation_persists_follow_up_with_three_business_day_due_date(self):
        service = TonyCommercialWatchCommandService(
            StubCommandService(self.confirmation_response()),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 14, 10, 0),  # Friday
        )

        response = service.execute("Execution confirmed", [])

        self.assertEqual(response.status, "healthy")
        payload = self.store.read_text(encoding="utf-8")
        self.assertIn('"contact": "Lesley Harman"', payload)
        self.assertIn('"email": "lesley@example.com"', payload)
        self.assertIn('"due_on": "2026-08-19"', payload)  # Wed: Mon/Tue/Wed are 3 business days

    def test_overdue_commitment_is_surfaced_as_executive_attention(self):
        self._seed_commitment()

        reader = TonyCommercialWatchCommandService(
            StubCommandService(CommandResponse("delegated", "healthy", "delegated", {})),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 20, 9, 0),
        )
        response = reader.execute("What needs my attention?", [])

        self.assertEqual(response.command, "commercial_watch")
        self.assertEqual(response.status, "attention")
        self.assertEqual(response.data["overdue_count"], 1)
        self.assertIn("Lesley Harman", response.message)
        self.assertIn("before starting lower-priority work", response.message)

    def test_morning_brief_is_augmented_when_commercial_follow_up_is_overdue(self):
        self._seed_commitment()

        base = StubCommandService(CommandResponse("morning", "healthy", "Morning brief is otherwise clear.", {"period": "morning"}))
        reader = TonyCommercialWatchCommandService(
            base,
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 20, 9, 0),
        )
        response = reader.execute("morning", [])

        self.assertEqual(response.status, "attention")
        self.assertIn("Commercial attention", response.message)
        self.assertEqual(response.data["commercial_watch"]["overdue_count"], 1)

    def test_positive_gmail_reply_resolves_commitment_and_escalates(self):
        self._seed_commitment()
        base = StubCommandService(CommandResponse("delegated", "healthy", "delegated", {}))
        service = TonyCommercialWatchCommandService(
            base,
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 17, 9, 30),
        )

        response = service.execute(
            "Gmail reply received",
            [
                {
                    "provider": "gmail",
                    "event": "reply_received",
                    "lead_id": "lesley-1",
                    "message_id": "msg-123",
                    "from": "lesley@example.com",
                    "subject": "Re: growth",
                    "body": "Thanks, this sounds good. Happy to chat next week.",
                }
            ],
        )

        self.assertEqual(response.command, "commercial_reply")
        self.assertEqual(response.status, "attention")
        self.assertEqual(response.data["disposition"], "positive_intent")
        self.assertTrue(response.data["commitment_resolved"])
        self.assertIn("deserves attention now", response.message)
        stored = json.loads(self.store.read_text(encoding="utf-8"))[0]
        self.assertEqual(stored["status"], "resolved")
        self.assertEqual(stored["resolution_reason"], "reply_received")
        self.assertEqual(stored["reply"]["message_id"], "msg-123")
        self.assertEqual(base.calls, [])

    def test_automatic_reply_does_not_clear_follow_up(self):
        self._seed_commitment()
        service = TonyCommercialWatchCommandService(
            StubCommandService(CommandResponse("delegated", "healthy", "delegated", {})),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 17, 9, 30),
        )

        response = service.execute(
            "Gmail reply received",
            [
                {
                    "provider": "gmail",
                    "event": "reply_received",
                    "lead_id": "lesley-1",
                    "subject": "Automatic reply: Re: growth",
                    "body": "I am currently out of office and will return next week.",
                }
            ],
        )

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["intent"], "ignore_automatic_reply")
        self.assertFalse(response.data["commitment_resolved"])
        stored = json.loads(self.store.read_text(encoding="utf-8"))[0]
        self.assertEqual(stored["status"], "pending")

    def test_decline_resolves_follow_up_without_false_escalation(self):
        self._seed_commitment()
        service = TonyCommercialWatchCommandService(
            StubCommandService(CommandResponse("delegated", "healthy", "delegated", {})),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 17, 9, 30),
        )

        response = service.execute(
            "Gmail reply received",
            [
                {
                    "provider": "gmail",
                    "direction": "inbound",
                    "lead_id": "lesley-1",
                    "body": "Thanks for reaching out, but we're not interested at the moment.",
                }
            ],
        )

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["disposition"], "declined")
        self.assertTrue(response.data["commitment_resolved"])
        self.assertIn("No immediate escalation", response.message)

    def test_unmatched_gmail_reply_does_not_mutate_commitments(self):
        self._seed_commitment()
        service = TonyCommercialWatchCommandService(
            StubCommandService(CommandResponse("delegated", "healthy", "delegated", {})),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 17, 9, 30),
        )

        response = service.execute(
            "Gmail reply received",
            [{"provider": "gmail", "event": "reply_received", "lead_id": "other-lead", "body": "Interested."}],
        )

        self.assertEqual(response.status, "attention")
        self.assertEqual(response.data["intent"], "reconcile_unmatched_commercial_reply")
        self.assertFalse(response.data["commitment_resolved"])
        stored = json.loads(self.store.read_text(encoding="utf-8"))[0]
        self.assertEqual(stored["status"], "pending")


if __name__ == "__main__":
    unittest.main()
