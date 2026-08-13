from __future__ import annotations

import unittest

from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_command_service import CommandResponse


class StubService:
    def __init__(self) -> None:
        self.mission_control_loader = lambda: None
        self.execution_journal = object()
        self.github_configured = True
        self.calls = []
        self.response = CommandResponse("delegated", "healthy", "delegated", {})

    def execute(self, command, objects):
        records = list(objects)
        self.calls.append((command, records))
        return self.response


class TonyCapabilityCommandServiceTests(unittest.TestCase):
    def test_capabilities_returns_machine_readable_registry(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        response = service.execute("/capabilities", [])
        self.assertEqual(response.command, "capabilities")
        self.assertEqual(response.data["total_count"], 14)
        self.assertTrue(any(item["command"] == "/mission" for item in response.data["capabilities"]))
        self.assertTrue(any(item["command"] == "/github" for item in response.data["capabilities"]))
        self.assertTrue(any(item["command"] == "/friday" for item in response.data["capabilities"]))
        self.assertTrue(any(item["command"] == "/vocabulary" for item in response.data["capabilities"]))
        self.assertEqual(base.calls, [])

    def test_help_and_commands_are_aliases(self):
        service = TonyCapabilityCommandService(StubService())
        self.assertEqual(service.execute("/help", []).command, "capabilities")
        self.assertEqual(service.execute("/commands", []).command, "capabilities")

    def test_unconfigured_features_are_reported_not_hidden(self):
        base = StubService()
        base.mission_control_loader = None
        base.execution_journal = None
        response = TonyCapabilityCommandService(base).execute("/capabilities", [])
        mission = next(item for item in response.data["capabilities"] if item["command"] == "/mission")
        history = next(item for item in response.data["capabilities"] if item["command"].startswith("/history"))
        self.assertFalse(mission["available"])
        self.assertFalse(history["available"])
        self.assertEqual(response.status, "partial")

    def test_non_capability_command_delegates(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        response = service.execute("/health", [{"id": "one"}])
        self.assertEqual(response.command, "delegated")
        self.assertEqual(base.calls, [("/health", [{"id": "one"}])])

    def test_mission_control_configuration_is_exposed_for_bridge_health(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        self.assertIs(service.mission_control_loader, base.mission_control_loader)

    def test_named_follow_up_uses_previous_lead_context_without_requery(self):
        base = StubService()
        base.response = CommandResponse(
            "leads", "healthy", "raw", {
                "scope": "today",
                "leads": [
                    {
                        "lead_id": "lesley", "contact": "Lesley Harman",
                        "company": "Harman Communications Ltd", "email": "lesley@example.com",
                        "source": "Tally", "status": "New", "pipeline_stage": "New Diagnostic",
                        "lead_temperature": "Warm", "ai_summary": "Growth is limited by confused outreach.",
                        "recommended_next_action": "Invite Lesley to discovery.",
                    },
                    {
                        "lead_id": "jimmy", "contact": "Jimmy Diamond",
                        "company": "Jimmy Diamond Ltd", "email": "jimmy@example.com",
                        "source": "Tally", "status": "New", "pipeline_stage": "New Diagnostic",
                        "lead_temperature": "Warm", "ai_summary": "Needs a clearer growth story.",
                    },
                ],
            },
        )
        service = TonyCapabilityCommandService(base)
        service.execute("What inbound leads did we get today?", [])
        response = service.execute("Tell me more about Lesley", [])
        self.assertEqual(response.command, "leads")
        self.assertEqual(response.data["count"], 1)
        self.assertIn("Lesley Harman", response.message)
        self.assertIn("Next: Invite Lesley to discovery.", response.message)
        self.assertNotIn("Jimmy Diamond", response.message)
        self.assertEqual(len(base.calls), 1)

    def test_follow_up_without_prior_lead_context_delegates(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        service.execute("Tell me more about Lesley", [])
        self.assertEqual(len(base.calls), 1)


if __name__ == "__main__":
    unittest.main()
