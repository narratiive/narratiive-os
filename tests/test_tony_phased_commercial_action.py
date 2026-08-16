from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService
from runtime.tony_persistent_autonomous_result import TonyPersistentAutonomousResultCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyPhasedCommercialActionTests(unittest.TestCase):
    NOW = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)

    def test_meeting_intent_preserves_full_recommendation_but_executes_calendar_read_first(self):
        context = {
            "worker": "Gmail",
            "dispatch": {
                "worker": "Gmail",
                "execution_mode": "autonomous_read",
                "instruction": "read the commercial reply thread",
                "target": {"lead_id": "lesley", "contact": "Lesley Harman", "area": "commercial"},
            },
            "evidence": {
                "summary": "Lesley replied: when are you free next week?",
                "thread_id": "thread-1",
                "read_only": True,
            },
            "executive_result": "Verified Gmail reply evidence returned.",
            "verified_at": self.NOW.isoformat(),
        }

        self.assertTrue(TonyCommercialAutonomousJudgementCommandService._enrich_context(context))
        evidence = context["evidence"]
        self.assertIn("two suitable times", evidence["recommended_next_action"])
        self.assertEqual(
            evidence["execution_next_action"],
            "Check calendar availability for the next five business days.",
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            path.write_text(json.dumps(context), encoding="utf-8")
            service = TonyPersistentAutonomousResultCommandService(
                StubCommandService(),
                store_path=path,
                clock=lambda: self.NOW,
            )
            response = service.execute("OK, do that", [])

        self.assertEqual(response.data["grounded_next_action"], "Check calendar availability for the next five business days.")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Google Calendar")
        self.assertEqual(handoff["execution_mode"], "autonomous_read")
        self.assertFalse(handoff["approval_required"])
        self.assertTrue(handoff["dispatch"]["eligible"])
        self.assertNotIn("reply", handoff["action"].casefold())
        self.assertFalse(response.data["external_action_taken"])

    def test_verified_calendar_availability_advances_meeting_sequence_without_inventing_times(self):
        context = {
            "worker": "Google Calendar",
            "dispatch": {
                "worker": "Google Calendar",
                "execution_mode": "autonomous_read",
                "instruction": "prepare the required scheduling action without inventing availability: Check calendar availability for the next five business days.",
                "target": {"lead_id": "lesley", "contact": "Lesley Harman", "area": "commercial"},
            },
            "evidence": {
                "summary": "Available Tuesday 10:00-11:00 and Thursday 14:00-16:00.",
                "event_ids": ["calendar-window-1"],
                "read_only": True,
            },
            "executive_result": "Google Calendar completed the read-only check.",
            "verified_at": self.NOW.isoformat(),
        }

        self.assertTrue(TonyCommercialAutonomousJudgementCommandService._enrich_context(context))
        judgement = context["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "availability_verified")
        self.assertIn("Lesley Harman", judgement["recommended_next_action"])
        self.assertIn("verified Calendar result", judgement["recommended_next_action"])
        self.assertIn("Tuesday 10:00-11:00", context["evidence"]["verified_availability_summary"])
        self.assertNotIn("Tuesday 10:00-11:00", judgement["recommended_next_action"])

    def test_calendar_read_without_commercial_lead_context_does_not_create_reply_recommendation(self):
        context = {
            "worker": "Google Calendar",
            "dispatch": {
                "worker": "Google Calendar",
                "execution_mode": "autonomous_read",
                "instruction": "check calendar availability for next week",
                "target": {"area": "operations"},
            },
            "evidence": {
                "summary": "Available Tuesday morning.",
                "event_ids": ["calendar-window-1"],
                "read_only": True,
            },
            "executive_result": "Google Calendar completed the read-only check.",
            "verified_at": self.NOW.isoformat(),
        }

        self.assertFalse(TonyCommercialAutonomousJudgementCommandService._enrich_context(context))
        self.assertNotIn("commercial_judgement", context)
        self.assertNotIn("recommended_next_action", context["evidence"])

    def test_non_composite_recommendation_keeps_existing_action_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            path.write_text(
                json.dumps(
                    {
                        "worker": "Gmail",
                        "dispatch": {
                            "worker": "Gmail",
                            "execution_mode": "autonomous_read",
                            "target": {"lead_id": "lesley", "contact": "Lesley Harman", "area": "commercial"},
                        },
                        "evidence": {
                            "summary": "Lesley is interested.",
                            "recommended_next_action": "Reply to Lesley and suggest a discovery conversation.",
                            "thread_id": "thread-1",
                            "read_only": True,
                        },
                        "executive_result": "Verified Gmail reply evidence returned.",
                        "verified_at": self.NOW.isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            service = TonyPersistentAutonomousResultCommandService(
                StubCommandService(),
                store_path=path,
                clock=lambda: self.NOW,
            )
            response = service.execute("Go ahead", [])

        self.assertEqual(response.data["execution_handoff"]["worker"], "Gmail")
        self.assertEqual(response.data["execution_handoff"]["execution_mode"], "approval_gated_write")
        self.assertTrue(response.data["execution_handoff"]["approval_granted"])


if __name__ == "__main__":
    unittest.main()
