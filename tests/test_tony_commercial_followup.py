from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_followup import TonyCommercialFollowupCommandService


class Stub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "post_send_notion_sync",
            "healthy",
            "Notion update verified.",
            {
                "execution_status": "commercial_state_sync_verified",
                "gmail_message_id": "gmail-123",
                "commercial_state_sync": {
                    "lead_id": "lead-1",
                    "contact": "Alex Example",
                    "company": "Example Co",
                },
                "external_action_taken": True,
            },
        )


class TonyCommercialFollowupTests(unittest.TestCase):
    def _service(self, *, now, gmail, claude=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dispatchers = {"Gmail": gmail}
        if claude is not None:
            dispatchers["Claude"] = claude
        return TonyCommercialFollowupCommandService(
            Stub(),
            dispatchers=dispatchers,
            store_path=Path(tmp.name) / "followup.json",
            clock=lambda: now[0],
        )

    @staticmethod
    def no_reply_evidence():
        return {
            "read_only": True,
            "thread_id": "thread-123",
            "message_id": "gmail-123",
            "reply_found": False,
            "summary": "No new inbound reply is present in the verified thread.",
        }

    def test_verified_contacted_state_runs_read_only_monitor_and_persists_deadline(self):
        now = [datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)]
        calls = []

        def gmail(contract):
            calls.append(contract)
            self.assertEqual(contract["execution_mode"], "autonomous_read")
            self.assertEqual(contract["payload"]["gmail_message_id"], "gmail-123")
            self.assertIn("Do not send", contract["instruction"])
            return self.no_reply_evidence()

        service = self._service(now=now, gmail=gmail)
        response = service.execute("do that", ())

        self.assertEqual(len(calls), 1)
        self.assertEqual(response.data["execution_status"], "reply_monitor_active")
        monitor = response.data["reply_monitor"]
        self.assertEqual(monitor["status"], "active")
        self.assertEqual(monitor["follow_up_due_at"], "2026-08-20T09:00:00+00:00")
        self.assertIn("no genuine reply yet", response.message)

    def test_genuine_meeting_reply_branches_to_calendar_read_without_booking(self):
        now = [datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)]

        def gmail(_):
            reply = "Hi Matt, this sounds interesting. Happy to chat next week — when are you free?"
            return {
                "read_only": True,
                "thread_id": "thread-123",
                "message_id": "reply-456",
                "reply_found": True,
                "body": reply,
                "summary": reply,
            }

        service = self._service(now=now, gmail=gmail)
        response = service.execute("do that", ())

        self.assertEqual(response.data["execution_status"], "commercial_reply_next_step_ready")
        self.assertEqual(response.data["commercial_judgement"]["disposition"], "meeting_intent")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Google Calendar")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_read")
        self.assertIn("do not create", handoff["dispatch"]["instruction"].casefold())
        self.assertFalse(response.data["external_action_taken"])

    def test_no_reply_at_deadline_prepares_claude_follow_up_but_never_sends(self):
        now = [datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)]
        gmail_calls = []
        claude_calls = []

        def gmail(contract):
            gmail_calls.append(contract)
            return self.no_reply_evidence()

        def claude(contract):
            claude_calls.append(contract)
            self.assertEqual(contract["execution_mode"], "autonomous_prepare")
            self.assertIn("Do not send it", contract["instruction"])
            return {
                "email_subject": "One thought for Example Co",
                "email_body": "Hi Alex, I wanted to follow up with one useful thought from the work I shared. There is a clear opportunity to sharpen the commercial story without adding more marketing complexity. Happy to send the detail if useful.",
            }

        service = self._service(now=now, gmail=gmail, claude=claude)
        first = service.execute("do that", ())
        self.assertEqual(first.data["reply_monitor"]["follow_up_due_at"], "2026-08-19T09:00:00+00:00")

        now[0] = datetime(2026, 8, 19, 9, 1, tzinfo=timezone.utc)
        response = service.execute("check replies", ())

        self.assertEqual(len(gmail_calls), 2)
        self.assertEqual(len(claude_calls), 1)
        self.assertEqual(response.data["execution_status"], "follow_up_draft_prepared")
        self.assertIn("email_body", response.data["follow_up_draft_evidence"])
        self.assertIn("nothing has been sent", response.message.casefold())
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
