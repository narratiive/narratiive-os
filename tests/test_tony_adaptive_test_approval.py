from __future__ import annotations

import unittest

from runtime.tony_adaptive_test_approval import TonyAdaptiveTestApprovalCommandService
from runtime.tony_command_service import CommandResponse


class StubAdaptiveService:
    mission_control_loader = None
    github_configured = False

    def __init__(self):
        self.responses = []

    def execute(self, command, objects):
        return self.responses.pop(0) if self.responses else CommandResponse("delegated", "healthy", "delegated", {})


class TonyAdaptiveTestApprovalTests(unittest.TestCase):
    def service(self):
        stub = StubAdaptiveService()
        return TonyAdaptiveTestApprovalCommandService(stub), stub

    def prime_ready_review(self, service, stub):
        stub.responses.append(CommandResponse(
            "executive_adaptation_handoff",
            "healthy",
            "handoff",
            {
                "adaptation_status": "worker_handoff_ready",
                "handoff": {
                    "priority": {"key": "lead:lesley", "label": "Lesley Harman"},
                },
            },
        ))
        service.execute("Go ahead with the redesign", [])
        stub.responses.append(CommandResponse(
            "executive_adaptation_review",
            "healthy",
            "ready",
            {
                "adaptation_status": "ready_for_approval",
                "review": {
                    "option_count": 2,
                    "recommendation": "Use option A.",
                    "changed_variable": "opening proposition",
                    "success_signal": "Qualified reply within three business days",
                },
            },
        ))
        service.execute("Review what Claude returned", [])

    def test_approved_review_becomes_controlled_test_handoff(self):
        service, stub = self.service()
        self.prime_ready_review(service, stub)

        response = service.execute("Looks good, approve it", [])

        self.assertEqual(response.command, "executive_adaptive_test_approval")
        self.assertEqual(response.data["adaptation_status"], "approved_test_handoff_ready")
        package = response.data["execution_package"]
        self.assertTrue(package["action_id"].startswith("adaptive:lead:lesley:"))
        self.assertEqual(package["approved_design"]["changed_variable"], "opening proposition")
        self.assertIn("Qualified reply", package["approved_design"]["success_signal"])
        self.assertEqual(package["status"], "approved_awaiting_execution_confirmation")
        self.assertFalse(response.data["execution_performed"])
        self.assertFalse(package["external_action_taken"])

    def test_approval_without_ready_review_delegates(self):
        service, _ = self.service()
        response = service.execute("Approve it", [])
        self.assertEqual(response.command, "delegated")

    def test_revision_required_clears_approval_path(self):
        service, stub = self.service()
        stub.responses.append(CommandResponse(
            "executive_adaptation_handoff",
            "healthy",
            "handoff",
            {"adaptation_status": "worker_handoff_ready", "handoff": {"priority": {"key": "lead:lesley", "label": "Lesley Harman"}}},
        ))
        service.execute("Go ahead with the redesign", [])
        stub.responses.append(CommandResponse(
            "executive_adaptation_review",
            "attention",
            "revise",
            {"adaptation_status": "revision_required"},
        ))
        service.execute("Review the redesign", [])

        response = service.execute("Run the test", [])
        self.assertEqual(response.command, "delegated")


if __name__ == "__main__":
    unittest.main()
