from __future__ import annotations

import unittest

from runtime.tony_command_service import CommandResponse
from runtime.tony_conversational_intent import TonyConversationalIntentCommandService


class StubService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        normalized = " ".join(command.strip().split())
        if normalized == "What should I focus on today?":
            return CommandResponse(
                "agency_focus",
                "healthy",
                "Your first priority is the strongest verified commercial opportunity.",
                {"intent": "synthesise_agency_focus"},
            )
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        return CommandResponse(
            name,
            "error",
            f"Unsupported command: {name}",
            {"error_code": "unsupported_command"},
        )


class TonyConversationalIntentTests(unittest.TestCase):
    def setUp(self):
        self.service = TonyConversationalIntentCommandService(StubService())

    def test_natural_focus_question_never_leaks_to_first_word_parser(self):
        response = self.service.execute("what should I focus on today?", ())

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.command, "agency_focus")
        self.assertNotIn("Unsupported command", response.message)

    def test_discovery_invitation_is_treated_as_business_intent(self):
        response = self.service.execute("Invite Matt for a discovery call", ())

        self.assertEqual(response.status, "attention")
        self.assertEqual(response.data["intent"], "invite_to_discovery")
        self.assertEqual(response.data["person"], "Matt")
        self.assertTrue(response.data["legacy_command_fallback_suppressed"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertNotIn("Unsupported command", response.message)

    def test_unresolved_natural_language_fails_conversationally_not_as_cli_command(self):
        response = self.service.execute("Help me think about this client", ())

        self.assertEqual(response.command, "conversation")
        self.assertEqual(response.status, "attention")
        self.assertEqual(response.data["intent"], "unresolved_conversational_request")
        self.assertNotIn("Unsupported command", response.message)

    def test_unknown_explicit_slash_command_preserves_deterministic_command_error(self):
        response = self.service.execute("/does-not-exist", ())

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "unsupported_command")
        self.assertIn("Unsupported command", response.message)


if __name__ == "__main__":
    unittest.main()
