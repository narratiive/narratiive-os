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
        self.assertEqual(base.calls, [])

    def test_help_and_commands_are_aliases(self):
        service = TonyCapabilityCommandService(StubService())
        self.assertEqual(service.execute("/help", []).command, "capabilities")
        self.assertEqual(service.execute("/commands", []).command, "capabilities")

    def test_non_capability_command_delegates(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        response = service.execute("/health", [{"id": "one"}])
        self.assertEqual(response.command, "delegated")
        self.assertEqual(base.calls, [("/health", [{"id": "one"}])])

    def _lead_response(self):
        return CommandResponse("leads", "healthy", "raw", {"scope": "today", "leads": [
            {"lead_id": "lesley", "contact": "Lesley Harman", "company": "Harman Communications Ltd", "email": "lesley@example.com", "source": "Tally", "status": "New", "pipeline_stage": "New Diagnostic", "lead_temperature": "Warm", "ai_summary": "Growth is limited by confused outreach.", "recommended_next_action": "Invite Lesley to discovery."},
            {"lead_id": "jimmy", "contact": "Jimmy Diamond", "company": "Jimmy Diamond Ltd", "email": "jimmy@example.com", "source": "Tally", "status": "New", "pipeline_stage": "New Diagnostic", "lead_temperature": "Warm", "ai_summary": "Needs a clearer growth story."},
        ]})

    def test_named_follow_up_uses_previous_lead_context_without_requery(self):
        base = StubService()
        base.response = self._lead_response()
        service = TonyCapabilityCommandService(base)
        service.execute("What inbound leads did we get today?", [])
        response = service.execute("Tell me more about Lesley", [])
        self.assertEqual(response.data["count"], 1)
        self.assertIn("Lesley Harman", response.message)
        self.assertNotIn("Jimmy Diamond", response.message)
        self.assertEqual(len(base.calls), 1)

    def test_progress_lead_builds_execution_plan_without_claiming_execution(self):
        base = StubService()
        base.response = self._lead_response()
        service = TonyCapabilityCommandService(base)
        service.execute("What inbound leads did we get today?", [])
        response = service.execute("Let's pursue Lesley", [])
        self.assertEqual(response.command, "lead_action")
        self.assertEqual(response.data["intent"], "progress_lead")
        self.assertFalse(response.data["external_action_taken"])
        self.assertTrue(response.data["approval_required"])
        self.assertEqual([step["owner"] for step in response.data["execution_plan"]], ["Tony", "Claude", "Tony", "Matt"])
        self.assertIn("personalised first-touch approach", response.message)
        self.assertIn("Nothing has been sent or changed externally yet", response.message)
        self.assertEqual(len(base.calls), 1)

    def test_prepare_it_turns_active_lead_into_delegation_ready_brief(self):
        base = StubService()
        base.response = self._lead_response()
        service = TonyCapabilityCommandService(base)
        service.execute("What inbound leads did we get today?", [])
        service.execute("Let's pursue Lesley", [])
        response = service.execute("Go ahead and prepare it", [])
        self.assertEqual(response.command, "lead_preparation")
        self.assertEqual(response.data["intent"], "delegate_lead_preparation")
        self.assertEqual(response.data["delegation_status"], "ready")
        self.assertEqual(response.data["delegation_brief"]["owner"], "Claude")
        self.assertEqual(response.data["delegation_brief"]["reviewer"], "Tony")
        self.assertEqual(response.data["delegation_brief"]["contact"], "Lesley Harman")
        self.assertTrue(response.data["approval_required_for_send"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("have not claimed delegation or external execution", response.message)
        self.assertEqual(len(base.calls), 1)

    def test_prepare_without_active_decision_delegates_normally(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        service.execute("Go ahead and prepare it", [])
        self.assertEqual(len(base.calls), 1)

    def test_follow_up_without_prior_lead_context_delegates(self):
        base = StubService()
        service = TonyCapabilityCommandService(base)
        service.execute("Tell me more about Lesley", [])
        self.assertEqual(len(base.calls), 1)


if __name__ == "__main__":
    unittest.main()
