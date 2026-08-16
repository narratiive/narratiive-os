from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyCalendarReplyPreparationTests(unittest.TestCase):
    NOW = datetime(2026, 8, 16, 11, 0, tzinfo=timezone.utc)
    AVAILABILITY = "Tuesday 10:00-10:30 or Wednesday 14:00-14:30"

    def service(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Path(tmp.name) / "result.json"
        store.write_text(
            json.dumps(
                {
                    "worker": "Google Calendar",
                    "dispatch": {
                        "worker": "Google Calendar",
                        "execution_mode": "autonomous_read",
                        "instruction": "Check calendar availability for the next five business days.",
                        "target": {
                            "lead_id": "lesley",
                            "contact": "Lesley Harman",
                            "area": "commercial",
                        },
                    },
                    "evidence": {
                        "availability": self.AVAILABILITY,
                        "read_only": True,
                    },
                    "executive_result": "Calendar returned verified availability.",
                    "verified_at": self.NOW.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        return TonyCommercialAutonomousJudgementCommandService(
            StubCommandService(),
            store_path=store,
            clock=lambda: self.NOW,
        )

    def test_verified_availability_prepares_grounded_reply_draft_before_any_send(self):
        service = self.service()

        recommendation = service.execute("What do you recommend?", [])
        judgement = recommendation.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "availability_verified")
        self.assertIn("discovery reply", judgement["recommended_next_action"])
        self.assertIn("two suitable times", judgement["recommended_next_action"])
        self.assertIn("Prepare a concise discovery response", judgement["execution_next_action"])
        self.assertIn(self.AVAILABILITY, judgement["execution_next_action"])
        self.assertIn("Do not send it", judgement["execution_next_action"])

        response = service.execute("OK, do that", [])

        self.assertEqual(response.command, "autonomous_result_action")
        self.assertEqual(response.data["execution_status"], "ready_for_handoff")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Claude")
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertFalse(handoff["approval_required"])
        self.assertTrue(handoff["dispatch"]["eligible"])
        self.assertEqual(handoff["dispatch"]["state"], "dispatcher_unavailable")
        self.assertEqual(handoff["dispatch"]["execution_truth"], "not_dispatched")
        self.assertIn("two suitable times", handoff["action"])
        self.assertIn(self.AVAILABILITY, handoff["action"])
        self.assertIn(self.AVAILABILITY, handoff["dispatch"]["instruction"])
        self.assertIn("Do not send it", handoff["action"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("no live dispatcher is configured", response.message)
        self.assertNotEqual(handoff["worker"], "Gmail")
        self.assertNotEqual(handoff["worker"], "Google Calendar")


if __name__ == "__main__":
    unittest.main()
