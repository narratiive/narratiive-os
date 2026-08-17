from __future__ import annotations

import unittest

from runtime.tony_command_service import CommandResponse
from runtime.tony_meeting_reply_preparation import TonyMeetingReplyPreparationCommandService


class Stub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "commercial_reply_monitor",
            "healthy",
            "I found a genuine verified reply from Alex Example.",
            {
                "execution_status": "commercial_reply_next_step_ready",
                "execution_handoff": {
                    "worker": "Google Calendar",
                    "approval_required": False,
                    "execution_mode": "autonomous_read",
                    "dispatch": {
                        "eligible": True,
                        "state": "ready_for_autonomous_dispatch",
                        "worker": "Google Calendar",
                        "instruction": "Check availability for the next five business days. Read only: do not create, move or delete any event.",
                        "target": {"lead_id": "lead-1", "contact": "Alex Example", "company": "Example Co", "area": "commercial"},
                        "execution_mode": "autonomous_read",
                        "expected_evidence": "verified read evidence",
                        "return_to": "Tony",
                        "execution_truth": "not_dispatched",
                        "payload": {"kind": "commercial_calendar_availability"},
                    },
                },
                "external_action_taken": False,
            },
        )


class TonyMeetingReplyPreparationTests(unittest.TestCase):
    def test_verified_calendar_availability_autonomously_prepares_grounded_reply(self):
        calls = []
        availability = {"read_only": True, "calendar_id": "primary", "availability": "Tue 18 Aug 10:00-10:30; Wed 19 Aug 14:00-14:30; Thu 20 Aug 09:30-10:00"}

        def calendar(contract):
            calls.append(("calendar", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_read")
            self.assertIn("do not create", contract["instruction"].casefold())
            return availability

        def claude(contract):
            calls.append(("claude", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_prepare")
            self.assertIn("exactly two suitable times", contract["instruction"])
            self.assertIn("Tue 18 Aug 10:00-10:30", contract["instruction"])
            self.assertIn("Do not send", contract["instruction"])
            return {"draft": "Hi Alex, great to hear. I can do Tuesday 18 August at 10:00 or Wednesday 19 August at 14:00. If either works, happy to confirm the conversation."}

        service = TonyMeetingReplyPreparationCommandService(Stub(), {"Google Calendar": calendar, "Claude": claude})
        response = service.execute("check replies", ())

        self.assertEqual([name for name, _ in calls], ["calendar", "claude"])
        self.assertEqual(response.data["execution_status"], "meeting_reply_draft_prepared")
        self.assertEqual(response.data["calendar_availability_evidence"], availability)
        self.assertIn("draft", response.data["meeting_reply_draft_evidence"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertNotIn("execution_handoff", response.data)
        self.assertIn("Nothing has been sent and no meeting has been booked", response.message)

    def test_missing_calendar_dispatcher_never_claims_availability_or_booking(self):
        service = TonyMeetingReplyPreparationCommandService(Stub(), {})
        response = service.execute("check replies", ())

        self.assertEqual(response.data["execution_status"], "calendar_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("no live Google Calendar read dispatcher", response.message)
        self.assertIn("Nothing has been sent or booked", response.message)


if __name__ == "__main__":
    unittest.main()
