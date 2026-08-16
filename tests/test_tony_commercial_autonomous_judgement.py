from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response

    def execute(self, command, objects):
        return self.response


def commercial_read_response() -> CommandResponse:
    return CommandResponse(
        command="agency_focus_action",
        status="healthy",
        message="Commercial evidence check prepared.",
        data={
            "execution_handoff": {
                "worker": "Gmail",
                "approval_required": False,
                "execution_truth": "handoff_prepared_only",
                "dispatch": {
                    "eligible": True,
                    "state": "ready_for_autonomous_dispatch",
                    "worker": "Gmail",
                    "instruction": "review the verified reply email thread for this lead",
                    "target": {"lead_id": "lesley", "area": "commercial"},
                    "execution_mode": "autonomous_read",
                    "expected_evidence": "decision-grade commercial read",
                    "return_to": "Tony",
                    "execution_truth": "not_dispatched",
                },
            }
        },
    )


def meeting_draft_response() -> CommandResponse:
    availability = "Tuesday 10:00-10:30 or Wednesday 14:00-14:30"
    instruction = (
        "Prepare a concise discovery response for Lesley Harman. "
        f"The verified Calendar availability is: {availability}. "
        "Use exactly two suitable times from that evidence. Do not send it, create a calendar event, or invent any availability."
    )
    return CommandResponse(
        command="autonomous_result_action",
        status="healthy",
        message="Meeting draft preparation ready.",
        data={
            "execution_handoff": {
                "worker": "Claude",
                "approval_required": False,
                "execution_truth": "handoff_prepared_only",
                "dispatch": {
                    "eligible": True,
                    "state": "ready_for_autonomous_dispatch",
                    "worker": "Claude",
                    "instruction": instruction,
                    "target": {
                        "lead_id": "lesley",
                        "contact": "Lesley Harman",
                        "area": "commercial",
                    },
                    "execution_mode": "autonomous_prepare",
                    "expected_evidence": "returned draft",
                    "return_to": "Tony",
                    "execution_truth": "not_dispatched",
                },
            }
        },
    )


class TonyCommercialAutonomousJudgementTests(unittest.TestCase):
    def service(self, evidence):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return TonyCommercialAutonomousJudgementCommandService(
            StubCommandService(commercial_read_response()),
            dispatchers={"Gmail": lambda contract: evidence},
            store_path=Path(tmp.name) / "result.json",
        )

    def meeting_draft_service(self, evidence):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return TonyCommercialAutonomousJudgementCommandService(
            StubCommandService(meeting_draft_response()),
            dispatchers={"Claude": lambda contract: evidence},
            store_path=Path(tmp.name) / "result.json",
        )

    def test_meeting_intent_recommends_calendar_check_before_reply(self):
        service = self.service(
            {
                "thread_id": "thread-1",
                "read_only": True,
                "summary": "Lesley is interested and asked for our availability next week.",
                "recommended_next_action": "Discount the work by 50%.",
            }
        )

        response = service.execute("do the first one", [])

        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "meeting_intent")
        self.assertEqual(judgement["judgement_owner"], "Tony")
        self.assertIn("Check calendar availability", judgement["recommended_next_action"])
        self.assertIn("two suitable times", judgement["recommended_next_action"])
        self.assertNotIn("Discount", judgement["recommended_next_action"])
        self.assertIn("signalling a conversation", response.message)

        follow_up = service.execute("What do you recommend?", [])
        self.assertIn("Check calendar availability", follow_up.message)
        self.assertNotIn("Discount", follow_up.message)

    def test_information_request_answers_question_before_forcing_meeting(self):
        service = self.service(
            {
                "thread_id": "thread-info",
                "read_only": True,
                "summary": "This sounds interesting. Can you tell me more about what the first phase would involve?",
            }
        )

        response = service.execute("do the first one", [])

        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "information_request")
        self.assertIn("tailored answer", judgement["recommended_next_action"])
        self.assertIn("do not force a meeting", judgement["recommended_next_action"])
        self.assertIn("want more substance before a meeting", response.message)

    def test_general_positive_interest_keeps_discovery_as_option(self):
        service = self.service(
            {
                "thread_id": "thread-positive",
                "read_only": True,
                "summary": "Thanks, I'm interested. This sounds good.",
            }
        )

        response = service.execute("do the first one", [])

        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "positive_intent")
        self.assertIn("suggest a discovery conversation", judgement["recommended_next_action"])
        self.assertIn("positive commercial intent", response.message)

    def test_decline_produces_close_record_recommendation(self):
        service = self.service(
            {
                "thread_id": "thread-2",
                "read_only": True,
                "content": "Thanks for reaching out, but we're not interested.",
            }
        )

        response = service.execute("do the first one", [])

        self.assertEqual(response.data["commercial_judgement"]["disposition"], "declined")
        self.assertIn("Update the lead record", response.data["commercial_judgement"]["recommended_next_action"])
        self.assertIn("this is a decline", response.message)

    def test_automatic_or_ambiguous_reply_does_not_invent_consequential_action(self):
        automatic = self.service(
            {
                "thread_id": "thread-3",
                "read_only": True,
                "summary": "Automatic reply: I am out of office until Monday.",
            }
        ).execute("do the first one", [])
        self.assertEqual(automatic.data["commercial_judgement"]["disposition"], "automatic_reply")
        self.assertEqual(automatic.data["commercial_judgement"]["recommended_next_action"], "")

        ambiguous_service = self.service(
            {
                "thread_id": "thread-4",
                "read_only": True,
                "summary": "Thanks for the note. I have passed this to my colleague.",
            }
        )
        ambiguous = ambiguous_service.execute("do the first one", [])
        self.assertEqual(ambiguous.data["commercial_judgement"]["disposition"], "reply_received")
        self.assertEqual(ambiguous.data["commercial_judgement"]["recommended_next_action"], "")
        recommendation = ambiguous_service.execute("What do you recommend?", [])
        self.assertIn("not enough grounded next-action evidence", recommendation.message)

    def test_returned_meeting_draft_is_reviewed_against_verified_times_before_send(self):
        service = self.meeting_draft_service(
            {
                "draft": (
                    "Hi Lesley, thanks for getting back to me. It would be great to talk. "
                    "I can do Tuesday at 10:00 or Wednesday at 14:00. If either works for you, "
                    "I’ll make sure we have the time set aside and we can pick up the growth challenge from there."
                )
            }
        )

        response = service.execute("OK, do that", [])

        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "meeting_draft_ready")
        self.assertEqual(judgement["review_status"], "ready_for_approval")
        self.assertTrue(all(judgement["review_checks"].values()))
        self.assertIn("Send the reviewed discovery reply", judgement["recommended_next_action"])
        self.assertIn("ready for approval", response.message)
        self.assertIn("Nothing has been sent externally", response.message)

        recommendation = service.execute("What do you recommend?", [])
        self.assertIn("Send the reviewed discovery reply", recommendation.message)

        approval = service.execute("OK, do that", [])
        handoff = approval.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Gmail")
        self.assertTrue(handoff["approval_required"])
        self.assertTrue(handoff["approval_granted"])
        self.assertEqual(handoff["dispatch"]["state"], "dispatcher_unavailable")
        self.assertEqual(handoff["dispatch"]["execution_truth"], "not_dispatched")
        self.assertFalse(approval.data["external_action_taken"])
        self.assertIn("no live dispatcher is configured", approval.message)

    def test_meeting_draft_with_invented_time_is_sent_back_for_revision(self):
        service = self.meeting_draft_service(
            {
                "draft": (
                    "Hi Lesley, thanks for getting back to me. It would be great to talk. "
                    "I can do Tuesday at 10:00 or Thursday at 16:00. If either works for you, "
                    "I’ll set aside the time and we can pick up the commercial challenge properly."
                ),
                "recommended_next_action": "Send this now.",
            }
        )

        response = service.execute("OK, do that", [])

        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "meeting_draft_revision_required")
        self.assertEqual(judgement["review_status"], "revision_required")
        self.assertFalse(judgement["review_checks"]["does_not_invent_times"])
        self.assertEqual(judgement["recommended_next_action"], "")
        self.assertIn("would not send it yet", response.message)

        recommendation = service.execute("What do you recommend?", [])
        self.assertIn("not enough grounded next-action evidence", recommendation.message)


if __name__ == "__main__":
    unittest.main()
