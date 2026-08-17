from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_discovery_outcome_tracking import TonyDiscoveryOutcomeTrackingCommandService


class BookingSyncStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "post_booking_notion_sync",
            "healthy",
            "Notion is now Discovery booked.",
            {
                "execution_status": "discovery_commercial_state_sync_verified",
                "calendar_event_id": "event-123",
                "notion_receipt": "notion-456",
                "discovery_tracking": {
                    "calendar_event_id": "event-123",
                    "lead_id": "lead-1",
                    "contact": "Alex Example",
                    "company": "Example Co",
                    "slot": {
                        "start": "2026-08-18T10:00:00+01:00",
                        "end": "2026-08-18T10:30:00+01:00",
                    },
                },
                "external_action_taken": True,
            },
        )


class TonyDiscoveryOutcomeTrackingTests(unittest.TestCase):
    def _service(self, dispatchers, now):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return TonyDiscoveryOutcomeTrackingCommandService(
            BookingSyncStub(),
            dispatchers=dispatchers,
            store_path=Path(tmp.name) / "discovery.json",
            clock=lambda: now[0],
        )

    def test_verified_booking_sync_starts_tracking_without_reading_meeting_tools(self):
        calls = []
        now = [datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)]
        service = self._service({"Fireflies": lambda contract: calls.append(contract) or {}}, now)

        response = service.execute("do that", ())

        self.assertEqual(response.data["execution_status"], "discovery_outcome_tracking_active")
        self.assertEqual(response.data["discovery_outcome_tracking"]["calendar_event_id"], "event-123")
        self.assertFalse(response.data["discovery_outcome_tracking"]["write_actions_allowed"])
        self.assertEqual(calls, [])
        self.assertIn("tracking the discovery outcome", response.message)

    def test_after_meeting_verified_fireflies_evidence_is_reviewed_by_claude_without_writes(self):
        now = [datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)]
        calls = []

        def fireflies(contract):
            calls.append(("fireflies", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_read")
            self.assertIn("Read only", contract["instruction"])
            return {
                "read_only": True,
                "event_id": "event-123",
                "transcript_id": "transcript-789",
                "transcript": "Alex confirmed a positioning problem, wants a sharper growth story and asked for a concrete proposal next week.",
                "summary": "Discovery attended with a clear request for a concrete proposal.",
            }

        def claude(contract):
            calls.append(("claude", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_prepare")
            self.assertIn("Distinguish meeting attendance from commercial success", contract["instruction"])
            self.assertIn("Do not send anything or update Notion", contract["instruction"])
            return {
                "summary": "The discovery produced a specific positioning need and a clear request for a proposal; this is a positive buying signal, not yet a win.",
                "recommendation": "Prepare a concise proposal grounded in the agreed positioning problem for Matt review.",
                "evidence_gaps": ["Budget and decision timing remain unverified."],
            }

        service = self._service({"Fireflies": fireflies, "Claude": claude}, now)
        service.execute("do that", ())
        now[0] = datetime(2026, 8, 18, 10, 45, tzinfo=timezone.utc)

        response = service.execute("what happened in discovery", ())

        self.assertEqual([name for name, _ in calls], ["fireflies", "claude"])
        self.assertEqual(response.data["execution_status"], "discovery_outcome_review_ready")
        outcome = response.data["discovery_outcome"]
        self.assertEqual(outcome["calendar_event_id"], "event-123")
        self.assertTrue(outcome["approval_required_for_next_write"])
        self.assertIn("Prepare a concise proposal", outcome["recommended_next_action"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("not yet a win", response.message)
        self.assertIn("approval-gated", response.message)

    def test_missing_fireflies_dispatcher_never_infers_meeting_outcome(self):
        now = [datetime(2026, 8, 18, 10, 45, tzinfo=timezone.utc)]
        service = self._service({}, now)
        service.execute("do that", ())

        response = service.execute("check discovery", ())

        self.assertEqual(response.data["execution_status"], "discovery_evidence_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("cannot verify attendance or meeting content", response.message)
        self.assertIn("No commercial outcome", response.message)


if __name__ == "__main__":
    unittest.main()
