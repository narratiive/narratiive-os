from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_post_discovery_proposal_execution import TonyPostDiscoveryProposalExecutionCommandService


PROPOSAL = (
    "The core business problem is that Example Co has a strong product but an unclear growth story, which is making it harder for buyers to understand why the offer matters now. "
    "Recommended scope: a focused strategic engagement covering market context, audience priorities, positioning, narrative and the practical commercial story required for activation. "
    "The intended outcomes are sharper strategic clarity, a more distinctive market position and a usable narrative system that improves sales and marketing decisions. "
    "The key evidence gap is final budget and internal decision timing, so those assumptions should remain explicit rather than being invented. "
    "The next step is for Matt to review this proposal and, if approved, send it to Alex for consideration before any further commercial commitment is made."
)


class ProposalDraftStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "post_discovery_commercial",
            "healthy",
            "The approved proposal preparation is complete and verified.",
            {
                "execution_status": "post_discovery_proposal_draft_ready",
                "proposal_evidence": {"work_product": PROPOSAL},
                "post_discovery_commercial": {
                    "state": "proposal_draft_ready",
                    "lead_id": "lead-1",
                    "contact": "Alex Example",
                    "company": "Example Co",
                    "calendar_event_id": "event-1",
                },
                "external_action_taken": False,
            },
        )


class TonyPostDiscoveryProposalExecutionTests(unittest.TestCase):
    def test_reviewed_proposal_requires_send_approval_then_notion_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def gmail(dispatch):
                calls.append(("gmail", dispatch))
                self.assertEqual(dispatch["execution_mode"], "approval_gated_write")
                self.assertTrue(dispatch["approval_granted"])
                self.assertEqual(dispatch["payload"]["email_subject"], "Proposal for Example Co")
                self.assertEqual(dispatch["payload"]["email_body"], PROPOSAL)
                return {"sent": True, "message_id": "proposal-msg-1", "thread_id": "thread-1"}

            def notion(dispatch):
                calls.append(("notion", dispatch))
                self.assertEqual(dispatch["execution_mode"], "approval_gated_write")
                self.assertEqual(dispatch["payload"]["status"], "Proposal sent")
                self.assertEqual(dispatch["payload"]["gmail_message_id"], "proposal-msg-1")
                return {"updated": True, "record_id": "notion-1"}

            service = TonyPostDiscoveryProposalExecutionCommandService(
                ProposalDraftStub(),
                {"Gmail": gmail, "Notion": notion},
                store_path=Path(tmp) / "state.json",
            )

            reviewed = service.execute("check proposal", ())
            self.assertEqual(reviewed.data["execution_status"], "post_discovery_proposal_ready_for_send_approval")
            self.assertEqual(calls, [])
            self.assertIn("Say 'send it'", reviewed.message)
            self.assertFalse(reviewed.data["proposal_review"]["external_action_taken"])

            sent = service.execute("send it", ())
            self.assertEqual([name for name, _ in calls], ["gmail"])
            self.assertEqual(sent.data["execution_status"], "proposal_send_verified_notion_approval_required")
            self.assertEqual(sent.data["gmail_message_id"], "proposal-msg-1")
            self.assertIn("Say 'do that'", sent.message)

            synced = service.execute("do that", ())
            self.assertEqual([name for name, _ in calls], ["gmail", "notion"])
            self.assertEqual(synced.data["execution_status"], "proposal_commercial_state_sync_verified")
            self.assertEqual(synced.data["notion_receipt"], "notion-1")
            self.assertIn("commercial success is still an outcome to track", synced.message)

    def test_weak_proposal_never_reaches_gmail(self):
        class WeakStub(ProposalDraftStub):
            def execute(self, command, objects):
                response = super().execute(command, objects)
                response.data["proposal_evidence"] = {"work_product": "Short proposal draft."}
                return response

        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            service = TonyPostDiscoveryProposalExecutionCommandService(
                WeakStub(),
                {"Gmail": lambda dispatch: calls.append(dispatch) or {"sent": True, "message_id": "bad"}},
                store_path=Path(tmp) / "state.json",
            )
            result = service.execute("check proposal", ())
            self.assertEqual(result.data["execution_status"], "post_discovery_proposal_revision_required")
            self.assertEqual(calls, [])
            self.assertIn("would not send", result.message)

    def test_unverified_gmail_send_does_not_prepare_notion_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyPostDiscoveryProposalExecutionCommandService(
                ProposalDraftStub(),
                {"Gmail": lambda dispatch: {"sent": False}},
                store_path=Path(tmp) / "state.json",
            )
            service.execute("check proposal", ())
            result = service.execute("send it", ())
            self.assertEqual(result.data["execution_status"], "proposal_send_unverified")
            self.assertFalse(result.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
