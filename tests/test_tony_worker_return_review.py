from __future__ import annotations

import unittest

from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_command_service import CommandResponse


class StubService:
    mission_control_loader = None
    github_configured = False

    def __init__(self) -> None:
        self.calls = []
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
        self.calls.append((command, list(objects)))
        return self.response


class TonyWorkerReturnReviewTests(unittest.TestCase):
    def _prepared_service(self) -> TonyCapabilityCommandService:
        service = TonyCapabilityCommandService(StubService())
        service.execute("What inbound leads did we get today?", [])
        service.execute("Let's pursue Lesley", [])
        service.execute("Go ahead and prepare it", [])
        return service

    def test_returned_worker_artifact_is_reviewed_without_claiming_send(self):
        service = self._prepared_service()
        draft = (
            "Hi Lesley, I noticed Harman Communications Ltd is dealing with confused outreach and uneven visibility. "
            "Narratiive could help sharpen the commercial story and turn that into a clearer route to growth. "
            "I would love to compare notes and see whether a short discovery conversation would be useful for you. "
            "If it is, I can suggest a couple of times next week."
        )
        response = service.execute(
            "Claude returned the draft — review it",
            [{"worker": "Claude", "artifact": draft}],
        )

        self.assertEqual(response.command, "delegated_work_review")
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["delegation_status"], "returned")
        self.assertEqual(response.data["review_status"], "ready_for_approval")
        self.assertTrue(response.data["approval_required_for_send"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("ready for your approval", response.message)
        self.assertIn("Nothing has been sent externally", response.message)

    def test_review_request_without_returned_artifact_fails_truthfully(self):
        service = self._prepared_service()
        response = service.execute("Review the returned draft", [])

        self.assertEqual(response.command, "delegated_work_review")
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["delegation_status"], "awaiting_artifact")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("don’t have a returned draft", response.message)

    def test_weak_return_is_sent_back_for_revision(self):
        service = self._prepared_service()
        response = service.execute(
            "Claude returned the draft",
            [{"worker": "Claude", "artifact": "Hi there. Would you like to chat about growth?"}],
        )

        self.assertEqual(response.data["review_status"], "revision_required")
        self.assertIn("would not put this in front of you yet", response.message)
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
