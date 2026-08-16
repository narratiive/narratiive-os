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


class TonyReviewedMeetingSendHandoffTests(unittest.TestCase):
    NOW = datetime(2026, 8, 16, 14, 0, tzinfo=timezone.utc)
    AVAILABILITY = "Tuesday 10:00-10:30 or Wednesday 14:00-14:30"
    DRAFT = (
        "Hi Lesley, thanks for coming back to me. It would be great to talk this through properly. "
        "I can do Tuesday at 10:00 or Wednesday at 14:00. If either works for you, I will get it booked in. "
        "Best, Matt"
    )

    def service(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Path(tmp.name) / "result.json"
        store.write_text(
            json.dumps(
                {
                    "worker": "Claude",
                    "dispatch": {
                        "worker": "Claude",
                        "execution_mode": "autonomous_prepare",
                        "instruction": (
                            "Prepare a concise discovery response for Lesley Harman. "
                            f"The verified Calendar availability is: {self.AVAILABILITY}. "
                            "Use exactly two suitable times from that evidence. "
                            "Do not send it, create a calendar event, or invent any availability."
                        ),
                        "target": {
                            "lead_id": "lesley",
                            "contact": "Lesley Harman",
                            "area": "commercial",
                        },
                    },
                    "evidence": {
                        "draft": self.DRAFT,
                        "work_product": self.DRAFT,
                    },
                    "executive_result": "Claude returned a grounded discovery reply draft.",
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

    def test_approval_carries_exact_reviewed_draft_into_gmail_handoff(self):
        service = self.service()

        review = service.execute("What do you recommend?", [])
        judgement = review.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "meeting_draft_ready")
        self.assertEqual(judgement["review_status"], "ready_for_approval")

        response = service.execute("OK, send it", [])

        self.assertEqual(response.command, "autonomous_result_action")
        self.assertEqual(response.data["execution_status"], "approved_for_execution")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Gmail")
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
        self.assertTrue(handoff["approval_required"])
        self.assertTrue(handoff["approval_granted"])
        self.assertEqual(handoff["approval_scope"], "grounded_next_action")
        self.assertIn(self.DRAFT, handoff["action"])
        self.assertIn(self.DRAFT, handoff["dispatch"]["instruction"])
        self.assertIn("exactly as reviewed", handoff["action"])
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
