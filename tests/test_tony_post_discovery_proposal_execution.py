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
    def test_legacy_text_cannot_replace_exact_pdf_and_fee_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            service = TonyPostDiscoveryProposalExecutionCommandService(ProposalDraftStub(),
                {'Gmail': lambda dispatch: calls.append(dispatch)}, store_path=Path(tmp)/'state.json')
            reviewed = service.execute('check proposal', ())
            self.assertEqual(reviewed.data['execution_status'], 'post_discovery_proposal_revision_required')
            service.execute('send it', ())
            self.assertEqual(calls, [])

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

    def test_restart_with_legacy_pending_send_cannot_dispatch(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            path.write_text(json.dumps({'pending_send': {'subject':'Old proposal', 'body':PROPOSAL}}))
            calls = []
            service = TonyPostDiscoveryProposalExecutionCommandService(ProposalDraftStub(),
                {'Gmail': lambda dispatch: calls.append(dispatch)}, store_path=path)
            result = service.execute('send it', ())
            self.assertEqual(result.data['execution_status'], 'legacy_proposal_send_blocked')
            self.assertFalse(result.data['external_action_taken'])
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
