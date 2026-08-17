from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_delivery_bootstrap import TonyDeliveryBootstrapCommandService


class StubService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse):
        self.response = response

    def execute(self, command, objects):
        return self.response


def onboarding_response():
    return CommandResponse(
        "client_onboarding",
        "healthy",
        "Onboarding kickoff verified.",
        {
            "execution_status": "onboarding_started_verified",
            "onboarding": {
                "onboarding_record_id": "onb-123",
                "opportunity_record_id": "opp-123",
                "lead_id": "lead-1",
                "contact": "Alex",
                "company": "Acme",
                "started": True,
            },
        },
    )


class TonyDeliveryBootstrapTests(unittest.TestCase):
    def test_verified_onboarding_requires_separate_delivery_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBootstrapCommandService(StubService(onboarding_response()), store_path=Path(tmp) / "delivery.json")
            response = service.execute("status", [])
            self.assertEqual(response.data["execution_status"], "delivery_bootstrap_approval_required")
            self.assertFalse(response.data["delivery_bootstrap"]["workspace_created"])
            self.assertFalse(response.data["external_action_taken"])

    def test_generic_approval_does_not_create_delivery_project(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBootstrapCommandService(StubService(onboarding_response()), dispatchers={"Notion": lambda dispatch: calls.append(dispatch)}, store_path=Path(tmp) / "delivery.json")
            service.execute("status", [])
            response = service.execute("do that", [])
            self.assertEqual(response.data["execution_status"], "delivery_bootstrap_approval_required")
            self.assertEqual(calls, [])

    def test_scoped_approval_requires_verified_notion_evidence(self):
        def notion(dispatch):
            return {"verified": True, "executed": True, "mutation_applied": True, "record_id": "delivery-1", "delivery_status": "Ready"}
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBootstrapCommandService(StubService(onboarding_response()), dispatchers={"Notion": notion}, store_path=Path(tmp) / "delivery.json")
            service.execute("status", [])
            response = service.execute("create delivery workspace", [])
            self.assertEqual(response.data["execution_status"], "delivery_bootstrap_verified")
            self.assertEqual(response.data["delivery_bootstrap"]["delivery_project_record_id"], "delivery-1")
            self.assertTrue(response.data["external_action_taken"])

    def test_missing_notion_dispatcher_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBootstrapCommandService(StubService(onboarding_response()), store_path=Path(tmp) / "delivery.json")
            service.execute("status", [])
            response = service.execute("create delivery workspace", [])
            self.assertEqual(response.data["execution_status"], "delivery_bootstrap_notion_dispatcher_unavailable")
            self.assertFalse(response.data["external_action_taken"])

    def test_pending_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery.json"
            first = TonyDeliveryBootstrapCommandService(StubService(onboarding_response()), store_path=path)
            first.execute("status", [])
            second = TonyDeliveryBootstrapCommandService(StubService(CommandResponse("status", "healthy", "ok", {})), store_path=path)
            response = second.execute("do that", [])
            self.assertEqual(response.data["delivery_bootstrap"]["onboarding_record_id"], "onb-123")


if __name__ == "__main__":
    unittest.main()
