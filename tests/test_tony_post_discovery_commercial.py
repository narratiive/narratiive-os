from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_post_discovery_commercial import TonyPostDiscoveryCommercialCommandService


class DiscoveryReviewStub:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("discovery_outcome", "healthy", "Verified discovery review ready.", {
            "execution_status": "discovery_outcome_review_ready",
            "discovery_outcome": {
                "calendar_event_id": "event-1", "lead_id": "lead-1", "contact": "Alex", "company": "Example Co",
                "meeting_evidence": {"transcript_id": "t-1", "summary": "Alex asked for a concrete proposal."},
                "review_evidence": {"summary": "Strong buying signal and clear proposal request.", "recommendation": "Prepare a concise proposal for Matt review."},
                "recommended_next_action": "Prepare a concise proposal for Matt review.",
            }, "external_action_taken": False,
        })


class TonyPostDiscoveryCommercialTests(unittest.TestCase):
    def test_positive_review_requires_preparation_approval_then_claude_only_prepares(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def claude(dispatch):
                calls.append(dispatch)
                self.assertTrue(dispatch["approval_granted"])
                self.assertIn("Do not send", dispatch["instruction"])
                draft = "Proposal draft for Example Co. Diagnosed problem: the growth story is not yet clear enough to support confident commercial choice. Recommended scope: a focused positioning and narrative sprint grounded in the discovery evidence. Intended outcomes: sharper strategic clarity, a stronger market story and a practical activation plan. Assumptions and evidence gaps: budget and final decision timing still need confirmation. Next step: Matt reviews this draft before any client-facing send."
                return {"work_product": draft, "summary": "Evidence-grounded proposal draft prepared for Tony review.", "result": draft}
            service = TonyPostDiscoveryCommercialCommandService(DiscoveryReviewStub(), {"Claude": claude}, store_path=Path(tmp)/"state.json")
            routed = service.execute("check discovery", ())
            self.assertEqual(routed.data["execution_status"], "post_discovery_proposal_approval_required")
            self.assertEqual(calls, [])
            self.assertIn("Say 'do that'", routed.message)
            prepared = service.execute("do that", ())
            self.assertEqual(len(calls), 1)
            self.assertEqual(prepared.data["execution_status"], "post_discovery_proposal_draft_ready")
            self.assertTrue(prepared.data["approval_required_for_send"])
            self.assertFalse(prepared.data["external_action_taken"])
            self.assertIn("nothing has been sent", prepared.message)

    def test_no_fit_review_never_prepares_or_changes_state(self):
        class NoFitStub(DiscoveryReviewStub):
            def execute(self, command, objects):
                response = super().execute(command, objects)
                response.data["discovery_outcome"]["review_evidence"] = {"summary": "No fit at present.", "recommendation": "Nurture and stop active proposal work."}
                response.data["discovery_outcome"]["recommended_next_action"] = "Nurture and stop active proposal work."
                return response
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            service=TonyPostDiscoveryCommercialCommandService(NoFitStub(), {"Claude": lambda d: calls.append(d) or {}}, store_path=Path(tmp)/"state.json")
            result=service.execute("check discovery", ())
            self.assertEqual(result.data["execution_status"], "post_discovery_no_proposal_recommended")
            self.assertEqual(calls, [])
            self.assertFalse(result.data["post_discovery_commercial"]["write_actions_allowed"])


if __name__ == "__main__": unittest.main()
