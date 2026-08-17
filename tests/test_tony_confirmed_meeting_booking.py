from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_confirmed_meeting_booking import TonyConfirmedMeetingBookingCommandService


SLOTS = [
    {
        "label": "Tuesday 10:00-10:30",
        "start": "2026-08-18T10:00:00+01:00",
        "end": "2026-08-18T10:30:00+01:00",
        "calendar_id": "primary",
    },
    {
        "label": "Wednesday 14:00-14:30",
        "start": "2026-08-19T14:00:00+01:00",
        "end": "2026-08-19T14:30:00+01:00",
        "calendar_id": "primary",
    },
]


class MeetingSequenceStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        if command == "prepare meeting reply":
            return CommandResponse(
                "commercial_meeting_reply",
                "healthy",
                "The reviewed discovery reply is ready for approval.",
                {
                    "execution_status": "meeting_reply_ready_for_approval",
                    "reply_monitor": {
                        "lead_id": "lead-1",
                        "contact": "Alex Example",
                        "company": "Example Co",
                    },
                    "calendar_availability_evidence": {
                        "read_only": True,
                        "calendar_id": "primary",
                        "available_slots": SLOTS,
                    },
                    "meeting_reply_draft_evidence": {
                        "draft": "Hi Alex. I can do Tuesday at 10:00 or Wednesday at 14:00."
                    },
                    "commercial_judgement": {"disposition": "meeting_draft_ready"},
                    "external_action_taken": False,
                },
            )
        if command == "send meeting reply":
            return CommandResponse(
                "autonomous_dispatch",
                "healthy",
                "The approved discovery reply was sent.",
                {
                    "execution_status": "approved_step_verified",
                    "commercial_judgement": {"disposition": "meeting_draft_ready"},
                    "dispatch_result": {
                        "worker": "Gmail",
                        "status": "verified",
                        "evidence": {
                            "sent": True,
                            "message_id": "meeting-reply-123",
                            "thread_id": "thread-123",
                        },
                    },
                    "external_action_taken": True,
                },
            )
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyConfirmedMeetingBookingTests(unittest.TestCase):
    def test_verified_confirmation_requires_booking_approval_then_calendar_proof(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        calls: list[tuple[str, dict]] = []

        def gmail(contract):
            calls.append(("gmail", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_read")
            return {
                "read_only": True,
                "reply_found": True,
                "body": "Tuesday at 10:00 works perfectly for me, thanks.",
                "summary": "Alex explicitly confirmed the offered Tuesday 10:00 discovery slot in the verified Gmail thread.",
                "message_id": "recipient-confirmation-456",
                "thread_id": "thread-123",
            }

        def calendar(contract):
            calls.append(("calendar", contract))
            self.assertEqual(contract["execution_mode"], "approval_gated_write")
            self.assertTrue(contract["approval_granted"])
            self.assertEqual(contract["payload"]["slot"]["start"], SLOTS[0]["start"])
            self.assertEqual(contract["payload"]["slot"]["end"], SLOTS[0]["end"])
            return {
                "created": True,
                "event_id": "event-789",
                "calendar_id": "primary",
                "summary": "Discovery with Alex Example",
            }

        service = TonyConfirmedMeetingBookingCommandService(
            MeetingSequenceStub(),
            dispatchers={"Gmail": gmail, "Google Calendar": calendar},
            store_path=Path(tmp.name) / "meeting-booking.json",
        )

        prepared = service.execute("prepare meeting reply", ())
        self.assertEqual(prepared.data["execution_status"], "meeting_reply_ready_for_approval")
        self.assertEqual(calls, [])

        sent = service.execute("send meeting reply", ())
        self.assertEqual(sent.data["execution_status"], "meeting_reply_sent_confirmation_monitor_active")
        self.assertTrue(sent.data["meeting_confirmation_monitor"]["approval_required_for_booking"])
        self.assertEqual(calls, [])

        confirmed = service.execute("check replies", ())
        self.assertEqual([name for name, _ in calls], ["gmail"])
        self.assertEqual(confirmed.data["execution_status"], "meeting_booking_approval_required")
        self.assertEqual(confirmed.data["meeting_confirmation"]["slot"]["start"], SLOTS[0]["start"])
        self.assertFalse(confirmed.data["external_action_taken"])
        self.assertIn("Say 'book it'", confirmed.message)

        booked = service.execute("book it", ())
        self.assertEqual([name for name, _ in calls], ["gmail", "calendar"])
        self.assertEqual(booked.data["execution_status"], "discovery_booking_verified")
        self.assertEqual(booked.data["calendar_booking"]["event_id"], "event-789")
        self.assertTrue(booked.data["external_action_taken"])

    def test_unmatched_reply_never_creates_calendar_event(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        calendar_calls: list[dict] = []

        def gmail(contract):
            return {
                "read_only": True,
                "reply_found": True,
                "body": "Thursday afternoon would be better for me.",
                "summary": "Alex replied in the verified Gmail thread asking for Thursday afternoon instead of either proposed slot.",
                "message_id": "recipient-other-456",
                "thread_id": "thread-123",
            }

        def calendar(contract):
            calendar_calls.append(contract)
            return {"created": True, "event_id": "should-not-run"}

        service = TonyConfirmedMeetingBookingCommandService(
            MeetingSequenceStub(),
            dispatchers={"Gmail": gmail, "Google Calendar": calendar},
            store_path=Path(tmp.name) / "meeting-booking.json",
        )
        service.execute("prepare meeting reply", ())
        service.execute("send meeting reply", ())

        response = service.execute("check replies", ())

        self.assertEqual(response.data["execution_status"], "meeting_confirmation_unmatched")
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(calendar_calls, [])
        self.assertIn("will not invent a booking", response.message)


if __name__ == "__main__":
    unittest.main()
