from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_post_booking_notion_sync import TonyPostBookingNotionSyncCommandService


class StubBookingService:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("meeting_booking", "healthy", "Booked with verified Calendar evidence.", {
            "execution_status": "discovery_booking_verified",
            "calendar_booking": {"state": "verified", "event_id": "evt-123", "lead_id": "lead-1", "contact": "Ada", "company": "Acme", "slot": {"start": "2026-08-20T10:00:00+01:00", "end": "2026-08-20T10:30:00+01:00"}},
            "calendar_evidence": {"event_id": "evt-123", "created": True},
            "external_action_taken": True,
        })


class TonyPostBookingNotionSyncTests(unittest.TestCase):
    def test_verified_booking_requires_separate_notion_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            service = TonyPostBookingNotionSyncCommandService(StubBookingService(), dispatchers={"Notion": lambda dispatch: calls.append(dispatch) or {"updated": True, "record_id": "notion-1"}}, store_path=Path(tmp) / "state.json")
            prepared = service.execute("book it", ())
            self.assertEqual(prepared.data["execution_status"], "calendar_verified_notion_approval_required")
            self.assertEqual(prepared.data["commercial_state_sync"]["status"], "Discovery booked")
            self.assertFalse(calls)
            completed = service.execute("do that", ())
            self.assertEqual(completed.data["execution_status"], "discovery_commercial_state_sync_verified")
            self.assertEqual(completed.data["notion_receipt"], "notion-1")
            self.assertEqual(calls[0]["payload"]["calendar_event_id"], "evt-123")
            self.assertEqual(calls[0]["payload"]["status"], "Discovery booked")

    def test_unverified_notion_write_remains_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyPostBookingNotionSyncCommandService(StubBookingService(), dispatchers={"Notion": lambda dispatch: {"updated": False}}, store_path=Path(tmp) / "state.json")
            service.execute("book it", ())
            result = service.execute("do that", ())
            self.assertEqual(result.data["execution_status"], "notion_sync_unverified")
            self.assertFalse(result.data["external_action_taken"])


if __name__ == "__main__": unittest.main()
