from __future__ import annotations

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
                },
                "follow_up_commitment": {
                    "owner": "Tony",
                    "action": "Check for a reply from Lesley Harman and surface the opportunity if there is no response within 3 business days.",
                    "status": "pending",
                },
            },
        )

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
        self.assertIn('"due_on": "2026-08-19"', payload)  # Wed: Mon/Tue/Wed are 3 business days

    def test_overdue_commitment_is_surfaced_as_executive_attention(self):
        writer = TonyCommercialWatchCommandService(
            StubCommandService(self.confirmation_response()),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 14, 10, 0),
        )
        writer.execute("Execution confirmed", [])

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
        writer = TonyCommercialWatchCommandService(
            StubCommandService(self.confirmation_response()),
            store_path=self.store,
            clock=lambda: datetime(2026, 8, 14, 10, 0),
        )
        writer.execute("Execution confirmed", [])

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


if __name__ == "__main__":
    unittest.main()
