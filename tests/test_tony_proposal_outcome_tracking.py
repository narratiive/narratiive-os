from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_proposal_outcome_tracking import TonyProposalOutcomeTrackingCommandService


class ProposalSentStub:
    mission_control_loader = None
    github_configured = False

    def __init__(self):
        self.state = {
            "last_completed": {
                "lead_id": "lead-1",
                "contact": "Alex Example",
                "company": "Example Co",
                "gmail_message_id": "proposal-msg-1",
                "notion_receipt": "notion-1",
            }
        }

    def execute(self, command, objects):
        return CommandResponse(
            "post_discovery_proposal",
            "healthy",
            "Confirmed. Proposal sent is authoritative in Notion.",
            {
                "execution_status": "proposal_commercial_state_sync_verified",
                "gmail_message_id": "proposal-msg-1",
                "notion_receipt": "notion-1",
                "external_action_taken": True,
            },
        )


class TonyProposalOutcomeTrackingTests(unittest.TestCase):
    def test_verified_acceptance_intent_is_not_treated_as_deal_won(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def gmail(dispatch):
                calls.append(dispatch)
                self.assertEqual(dispatch["execution_mode"], "autonomous_read")
                reply = "Thanks Alex. We'd like to proceed. Please send over the next steps."
                return {
                    "reply_found": True,
                    "message_id": "reply-1",
                    "thread_id": "thread-1",
                    "body": reply,
                    "summary": reply,
                    "read_only": True,
                }

            service = TonyProposalOutcomeTrackingCommandService(
                ProposalSentStub(),
                {"Gmail": gmail},
                store_path=Path(tmp) / "proposal-outcome.json",
                clock=lambda: datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc),
            )
            result = service.execute("do that", ())
            self.assertEqual(result.data["execution_status"], "proposal_outcome_verified")
            judgement = result.data["commercial_judgement"]
            self.assertEqual(judgement["disposition"], "proposal_acceptance_intent")
            self.assertFalse(judgement["deal_won"])
            self.assertIn("not a won deal", result.message)
            self.assertEqual(len(calls), 1)

    def test_verified_objection_may_prepare_but_never_send_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def gmail(dispatch):
                calls.append(("gmail", dispatch))
                reply = "We like the direction but have a question about budget and scope."
                return {
                    "reply_found": True,
                    "message_id": "reply-2",
                    "thread_id": "thread-1",
                    "body": reply,
                    "summary": reply,
                    "read_only": True,
                }

            def claude(dispatch):
                calls.append(("claude", dispatch))
                self.assertEqual(dispatch["execution_mode"], "autonomous_prepare")
                self.assertNotIn("send", dispatch.get("approval_scope", ""))
                return {
                    "email_subject": "Re: Example Co proposal",
                    "email_body": "Thanks for raising the budget and scope question. The proposal is deliberately focused on the strategic work required to resolve the growth problem first. I can clarify the scope boundaries and commercial assumptions before any commitment is made.",
                }

            service = TonyProposalOutcomeTrackingCommandService(
                ProposalSentStub(),
                {"Gmail": gmail, "Claude": claude},
                store_path=Path(tmp) / "proposal-outcome.json",
                clock=lambda: datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc),
            )
            result = service.execute("check proposal", ())
            self.assertEqual(result.data["commercial_judgement"]["disposition"], "proposal_objection_or_question")
            self.assertEqual(result.data["execution_handoff"]["execution_mode"], "autonomous_prepare")
            self.assertFalse(result.data["external_action_taken"])
            self.assertEqual([name for name, _ in calls], ["gmail", "claude"])

    def test_silence_after_three_business_days_prepares_follow_up_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)]
            calls = []

            def gmail(dispatch):
                calls.append(("gmail", dispatch))
                return {
                    "reply_found": False,
                    "thread_id": "thread-1",
                    "message_id": "proposal-msg-1",
                    "read_only": True,
                    "summary": "No new inbound reply is present in the verified proposal thread.",
                }

            def claude(dispatch):
                calls.append(("claude", dispatch))
                return {
                    "email_subject": "Quick follow-up on the proposal",
                    "email_body": "Hi Alex, one useful point to add to the proposal: the first phase is designed to turn the growth diagnosis into a practical decision framework quickly. If timing or scope is the blocker, I can clarify that directly. Nothing further is assumed until you are ready.",
                }

            service = TonyProposalOutcomeTrackingCommandService(
                ProposalSentStub(),
                {"Gmail": gmail, "Claude": claude},
                store_path=Path(tmp) / "proposal-outcome.json",
                clock=lambda: now[0],
            )
            first = service.execute("do that", ())
            self.assertEqual(first.data["execution_status"], "proposal_outcome_monitor_active")
            self.assertEqual([name for name, _ in calls], ["gmail"])

            now[0] = datetime(2026, 8, 20, 10, 1, tzinfo=timezone.utc)
            second = service.execute("proposal status", ())
            self.assertEqual(second.data["execution_status"], "proposal_follow_up_draft_prepared")
            self.assertFalse(second.data["external_action_taken"])
            self.assertEqual([name for name, _ in calls], ["gmail", "gmail", "claude"])


if __name__ == "__main__":
    unittest.main()
