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

    def execute(self, command, objects):
        records = list(objects)
        self.calls.append((command, records))
        return CommandResponse("delegated", "healthy", "delegated", {"records": records})


class TonyCapabilityCommandServiceTests(unittest.TestCase):
    def test_capabilities_returns_machine_readable_registry(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)

        response = service.execute("/capabilities", [])

        self.assertEqual(response.command, "capabilities")
        self.assertEqual(response.data["total_count"], 10)
        self.assertTrue(any(item["command"] == "/mission" for item in response.data["capabilities"]))
        self.assertTrue(any(item["command"] == "/github" for item in response.data["capabilities"]))
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


if __name__ == "__main__":
    unittest.main()
