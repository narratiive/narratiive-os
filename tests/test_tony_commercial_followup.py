from __future__ import annotations

import unittest
from datetime import datetime, timezone

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_followup import TonyCommercialFollowupCommandService


class Stub:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("post_send_notion_sync", "healthy", "Notion update verified.", {
            "execution_status": "commercial_state_sync_verified",
            "gmail_message_id": "gmail-123",
            "commercial_state_sync": {"lead_id": "lead-1", "contact": "Alex Example"},
            "external_action_taken": True,
        })


class TonyCommercialFollowupTests(unittest.TestCase):
    def test_verified_contacted_state_prepares_read_only_gmail_monitor(self):
        service = TonyCommercialFollowupCommandService(Stub(), clock=lambda: datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc))
        response = service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "reply_monitor_ready")
        monitor = response.data["reply_monitor"]
        self.assertEqual(monitor["status"], "active")
        self.assertEqual(monitor["follow_up_due_at"], "2026-08-20T09:00:00+00:00")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Gmail")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_read")
        self.assertEqual(handoff["dispatch"]["payload"]["gmail_message_id"], "gmail-123")
        self.assertIn("Do not send", handoff["dispatch"]["instruction"])
        self.assertIn("nothing will be sent without", response.message)

    def test_three_business_days_skip_weekend(self):
        service = TonyCommercialFollowupCommandService(Stub(), clock=lambda: datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc))
        response = service.execute("do that", ())
        self.assertEqual(response.data["reply_monitor"]["follow_up_due_at"], "2026-08-19T09:00:00+00:00")


if __name__ == "__main__": unittest.main()
