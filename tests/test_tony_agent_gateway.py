from __future__ import annotations

import json
import unittest
from unittest import mock

from openclaw.tony_agent_gateway import TonyAgentGateway, TonyAgentGatewayConfig, TonyAgentGatewayError


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self._raw


class TonyAgentGatewayTests(unittest.TestCase):
    def test_only_explicit_slash_commands_use_deterministic_surface(self):
        self.assertTrue(TonyAgentGateway.is_system_command("/health"))
        self.assertTrue(TonyAgentGateway.is_system_command("  /diagnostics"))
        self.assertFalse(TonyAgentGateway.is_system_command("Morning Tony, anything important?"))
        self.assertFalse(TonyAgentGateway.is_system_command("whta shoudl I focus on today?"))
        self.assertFalse(TonyAgentGateway.is_system_command("sort that out"))
        self.assertFalse(TonyAgentGateway.is_system_command("how is the research agent getting on?"))

    def test_gateway_preserves_session_and_agent_routing(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return _Response({"output_text": "Jimmy replied. I'd handle that first."})

        gateway = TonyAgentGateway(
            TonyAgentGatewayConfig(
                agent_id="tony",
                session_key="narratiive:tony:telegram",
                gateway_token="secret",
            )
        )
        with mock.patch("openclaw.tony_agent_gateway.urlopen", side_effect=fake_urlopen):
            self.assertEqual(gateway.converse("What did they say?"), "Jimmy replied. I'd handle that first.")

        self.assertEqual(captured["body"], {"model": "openclaw/tony", "input": "What did they say?"})
        headers = {key.casefold(): value for key, value in captured["headers"].items()}
        self.assertEqual(headers["x-openclaw-agent-id"], "tony")
        self.assertEqual(headers["x-openclaw-session-key"], "narratiive:tony:telegram")
        self.assertEqual(headers["authorization"], "Bearer secret")

    def test_acceptance_language_never_requires_phrase_matching(self):
        messages = (
            "Morning Tony, anything important?",
            "whta shoudl I focus on today?",
            "What did they say?",
            "sort that out",
            "use Thursday",
            "send it",
            "did it go?",
            "how is the strategy agent?",
            "how is the creative director getting on?",
            "what is production working on?",
        )
        for text in messages:
            with self.subTest(text=text):
                self.assertFalse(TonyAgentGateway.is_system_command(text))

    def test_slash_command_cannot_be_sent_to_agent_gateway(self):
        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with self.assertRaisesRegex(TonyAgentGatewayError, "slash commands"):
            gateway.converse("/health")


if __name__ == "__main__":
    unittest.main()
