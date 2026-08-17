from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService
from runtime.tony_meeting_reply_preparation import TonyMeetingReplyPreparationCommandService


DRAFT = (
    "Hi Alex, thanks for coming back to me. It would be great to talk this through properly. "
    "I can do Tuesday at 10:00 or Wednesday at 14:00. If either works for you, I will get it booked in. "
    "Best, Matt"
)


class NeutralStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


class MeetingHandoffStub:
    """Mirrors the live outer follow-up layer that creates the Calendar handoff."""

    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "commercial_reply_monitor",
            "healthy",
            "I found a genuine verified meeting-intent reply from Alex Example.",
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
                        "target": {
                            "lead_id": "lead-1",
                            "contact": "Alex Example",
                            "company": "Example Co",
                            "area": "commercial",
                        },
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


class TonyMeetingReplyReviewHandoffTests(unittest.TestCase):
    def test_verified_draft_is_reviewed_then_exact_send_requires_explicit_approval(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        calls: list[tuple[str, dict]] = []

        def calendar(contract):
            calls.append(("calendar", contract))
            return {
                "read_only": True,
                "calendar_id": "primary",
                "availability": "Tuesday 10:00-10:30 or Wednesday 14:00-14:30 or Thursday 09:30-10:00",
            }

        def claude(contract):
            calls.append(("claude", contract))
            return {"draft": DRAFT, "work_product": DRAFT}

        def gmail(contract):
            calls.append(("gmail", contract))
            self.assertTrue(contract["approval_granted"])
            self.assertEqual(contract["execution_mode"], "approval_gated_write")
            self.assertIn(DRAFT, contract["instruction"])
            return {
                "sent": True,
                "message_id": "meeting-reply-123",
                "thread_id": "thread-123",
                "summary": "The approved discovery reply was sent to Alex.",
            }

        dispatchers = {"Google Calendar": calendar, "Claude": claude, "Gmail": gmail}
        # In the live bridge the judgement/dispatch service is an inner layer. The
        # commercial follow-up layer outside it creates the Calendar handoff, and
        # the meeting-reply service consumes that handoff. Reproduce that shape
        # here so the test does not make the generic dispatcher execute Calendar
        # before the meeting-reply orchestration layer receives it.
        judgement = TonyCommercialAutonomousJudgementCommandService(
            NeutralStub(),
            dispatchers=dispatchers,
            store_path=Path(tmp.name) / "autonomous-result.json",
        )

        def sink(worker, dispatch, evidence, executive_result):
            verified, reason = judgement._verify_evidence(dispatch, evidence)
            self.assertTrue(verified, reason)
            context = {
                "worker": worker,
                "dispatch": dict(dispatch),
                "evidence": dict(evidence),
                "executive_result": executive_result,
                "verified_at": judgement._now().isoformat(),
            }
            self.assertTrue(judgement._enrich_context(context))
            judgement._last_verified_result = context
            judgement._persist_context(context)
            return dict(context)

        service = TonyMeetingReplyPreparationCommandService(
            MeetingHandoffStub(),
            dispatchers=dispatchers,
            verified_result_sink=sink,
        )

        prepared = service.execute("check replies", ())

        self.assertEqual(prepared.data["execution_status"], "meeting_reply_ready_for_approval")
        self.assertEqual(prepared.data["commercial_judgement"]["disposition"], "meeting_draft_ready")
        self.assertEqual(prepared.data["commercial_judgement"]["review_status"], "ready_for_approval")
        self.assertFalse(prepared.data["external_action_taken"])
        self.assertEqual([name for name, _ in calls], ["calendar", "claude"])
        self.assertIn("ready for your approval", prepared.message)
        self.assertIn("Nothing has been sent", prepared.message)

        # The next Telegram turn reaches the inner persistent judgement service,
        # where the reviewed context is already stored. Only this explicit approval
        # may turn the grounded recommendation into a Gmail write.
        sent = judgement.execute("OK, send it", ())

        self.assertEqual([name for name, _ in calls], ["calendar", "claude", "gmail"])
        self.assertEqual(sent.data["autonomous_dispatch_state"], "dispatch_verified")
        self.assertEqual(sent.data["execution_status"], "approved_step_verified")
        self.assertEqual(sent.data["dispatch_result"]["evidence"]["message_id"], "meeting-reply-123")
        self.assertIn("approved discovery reply was sent", sent.message)


if __name__ == "__main__":
    unittest.main()
