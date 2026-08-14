from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_outcome_accountability import TonyOutcomeAccountabilityCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self) -> None:
        self.calls = []
        self.completed = {
            "action_id": "lead:2026-08-14T10:00:00+00:00",
            "priority": {"label": "Lesley Harman", "key": "lead:lesley"},
            "completed_at": "2026-08-14T10:00:00+00:00",
            "completion_evidence": {"gmail_message_id": "msg-1"},
            "result_summary": "Follow-up prepared and returned.",
            "external_action_taken": False,
        }

    def execute(self, command, objects):
        self.calls.append(command)
        if command == "record_action_result":
            return CommandResponse(
                "agency_focus_action_result",
                "healthy",
                "Verified: the prepared action is complete.",
                {
                    "accepted": True,
                    "execution_status": "completed_verified",
                    "completed_action": dict(self.completed),
                    "external_action_taken": False,
                },
            )
        if command in {"morning", "evening"}:
            return CommandResponse(command, "healthy", "Daily brief", {"agency_state": {}})
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyOutcomeAccountabilityTests(unittest.TestCase):
    def service(self, store: Path, now: datetime | None = None):
        clock_now = now or datetime(2026, 8, 14, 11, 0, tzinfo=timezone.utc)
        return TonyOutcomeAccountabilityCommandService(
            StubCommandService(),
            store_path=store,
            clock=lambda: clock_now,
        )

    def test_verified_execution_is_not_claimed_as_business_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service(Path(tmp) / "outcomes.json")

            response = service.execute("record_action_result", [])

            self.assertEqual(response.command, "agency_focus_action_result")
            self.assertEqual(response.data["business_outcome_status"], "unverified")
            self.assertIn("business outcome is not yet verified", response.message)

            status = service.execute("Did that work?", [])
            self.assertEqual(status.command, "executive_outcome_status")
            self.assertEqual(status.data["business_outcome_status"], "unverified")
            self.assertIn("would not call it successful", status.message)

    def test_matching_positive_outcome_is_recorded_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "outcomes.json"
            service = self.service(store)
            service.execute("record_action_result", [])
            action_id = service._awaiting_outcome["action_id"]

            response = service.execute(
                "outcome_result",
                [{
                    "action_id": action_id,
                    "outcome_status": "positive",
                    "evidence": {"reply_id": "reply-1", "signal": "discovery accepted"},
                    "summary": "The prospect accepted a discovery conversation.",
                }],
            )

            self.assertTrue(response.data["accepted"])
            self.assertEqual(response.data["business_outcome_status"], "positive")
            self.assertIn("positive business outcome", response.message)

            restarted = self.service(store)
            status = restarted.execute("What was the outcome?", [])
            self.assertEqual(status.data["business_outcome_status"], "positive")
            self.assertIn("accepted a discovery conversation", status.message)

    def test_mismatched_outcome_cannot_mutate_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.service(Path(tmp) / "outcomes.json")
            service.execute("record_action_result", [])

            response = service.execute(
                "outcome_result",
                [{
                    "action_id": "wrong-action",
                    "outcome_status": "positive",
                    "evidence": {"signal": "something happened"},
                }],
            )

            self.assertFalse(response.data["accepted"])
            self.assertIsNotNone(service._awaiting_outcome)
            self.assertIsNone(service._last_outcome)

    def test_old_completed_action_surfaces_outcome_check_in_daily_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "outcomes.json"
            first = self.service(store)
            first.execute("record_action_result", [])

            later = TonyOutcomeAccountabilityCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: datetime(2026, 8, 15, 12, 1, tzinfo=timezone.utc),
                check_after=timedelta(hours=24),
            )
            response = later.execute("morning", [])

            self.assertEqual(response.status, "attention")
            self.assertIn("Outcome check", response.message)
            self.assertEqual(response.data["executive_outcome_watch"]["status"], "outcome_unverified")


if __name__ == "__main__":
    unittest.main()
