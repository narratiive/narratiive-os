from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        if command == "morning":
            return CommandResponse(
                "morning",
                "attention",
                "brief",
                {
                    "agency_state": {"executive_items": []},
                    "commercial_watch": {
                        "positive_replies": [
                            {
                                "lead_id": "lead-1",
                                "contact": "Test Lead",
                                "company": "Test Co",
                                "recommended_next_action": "Review the reply and decide the next commercial move.",
                            }
                        ],
                        "overdue": [],
                    },
                },
            )
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyStalledActionRetryTests(unittest.TestCase):
    def test_explicit_retry_reissues_stalled_worker_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            start = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)
            first = TonyPersistentAgencyFocusCommandService(
                StubCommandService(), store_path=store, clock=lambda: start
            )
            first.execute("What should I focus on today?", [])
            prepared = first.execute("OK, do that", [])
            self.assertEqual(prepared.data["execution_handoff"]["worker"], "Gmail")

            later = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start + timedelta(hours=3),
            )
            later.execute("What should I focus on today?", [])
            retried = later.execute("OK, do that", [])

            self.assertEqual(retried.command, "agency_focus_action_retry")
            self.assertTrue(retried.data["stale_action_reissued"])
            self.assertEqual(retried.data["execution_handoff"]["worker"], "Gmail")
            self.assertIsNone(later._pending_action)
            self.assertIn("reissuing", retried.message)

    def test_recent_duplicate_remains_suppressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            start = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)
            service = TonyPersistentAgencyFocusCommandService(
                StubCommandService(), store_path=store, clock=lambda: start
            )
            service.execute("What should I focus on today?", [])
            service.execute("OK, do that", [])
            duplicate = service.execute("OK, do that", [])

            self.assertEqual(duplicate.command, "agency_focus_action_status")
            self.assertTrue(duplicate.data["duplicate_handoff_suppressed"])
            self.assertIsNotNone(service._pending_action)


if __name__ == "__main__":
    unittest.main()
