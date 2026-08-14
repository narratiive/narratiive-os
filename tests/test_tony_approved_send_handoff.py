from __future__ import annotations

import unittest

from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_command_service import CommandResponse


class StubService:
    mission_control_loader = None
    github_configured = False

    def __init__(self) -> None:
        self.response = CommandResponse(
            "leads",
            "healthy",
            "raw",
            {
                "scope": "today",
                "leads": [
                    {
                        "lead_id": "lesley",
                        "contact": "Lesley Harman",
                        "company": "Harman Communications Ltd",
                        "email": "lesley@example.com",
                        "source": "Tally",
                        "status": "New",
                        "pipeline_stage": "New Diagnostic",
                        "lead_temperature": "Warm",
                        "ai_summary": "Growth is limited by confused outreach.",
                        "recommended_next_action": "Invite Lesley to discovery.",
                    }
                ],
            },
        )

    def execute(self, command, objects):
        return self.response


class TonyApprovedSendHandoffTests(unittest.TestCase):
    def _reviewed_service(self) -> TonyCapabilityCommandService:
        service = TonyCapabilityCommandService(StubService())
        service.execute("What inbound leads did we get today?", [])
        service.execute("Let's pursue Lesley", [])
        service.execute("Go ahead and prepare it", [])
        draft = (
            "Hi Lesley, I noticed Harman Communications Ltd is dealing with confused outreach and uneven visibility. "
            "Narratiive could help sharpen the commercial story and turn that into a clearer route to growth. "
            "I would love to compare notes and see whether a short discovery conversation would be useful for you. "
            "If it is, I can suggest a couple of times next week."
        )
        review = service.execute("Claude returned the draft", [{"worker": "Claude", "artifact": draft}])
        self.assertEqual(review.data["review_status"], "ready_for_approval")
        return service

    def test_approval_creates_gmail_and_notion_execution_package_without_claiming_execution(self):
        service = self._reviewed_service()
        response = service.execute("Looks good, send it", [])

        self.assertEqual(response.command, "approved_outreach_handoff")
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["execution_status"], "awaiting_confirmation")
        self.assertTrue(response.data["approval_received"])
        self.assertFalse(response.data["external_action_taken"])
        package = response.data["execution_package"]
        self.assertEqual(package["gmail"]["action"], "send_email")
        self.assertEqual(package["gmail"]["recipient"], "lesley@example.com")
        self.assertTrue(package["gmail"]["require_confirmation"])
        self.assertEqual(package["notion"]["action"], "update_lead_after_confirmed_send")
        self.assertEqual(package["notion"]["status"], "Contacted")
        self.assertIn("awaiting confirmed execution", response.message)

    def test_approval_before_reviewed_draft_is_rejected_truthfully(self):
        service = TonyCapabilityCommandService(StubService())
        service.execute("What inbound leads did we get today?", [])
        service.execute("Let's pursue Lesley", [])
        response = service.execute("Send it", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["execution_status"], "not_ready")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("Nothing has been sent", response.message)

    def test_weak_return_cannot_be_approved_for_execution(self):
        service = TonyCapabilityCommandService(StubService())
        service.execute("What inbound leads did we get today?", [])
        service.execute("Let's pursue Lesley", [])
        service.execute("Go ahead and prepare it", [])
        review = service.execute("Claude returned the draft", [{"worker": "Claude", "artifact": "Hi there. Want to chat about growth?"}])
        self.assertEqual(review.data["review_status"], "revision_required")

        response = service.execute("Approved, send it", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["execution_status"], "not_ready")
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
