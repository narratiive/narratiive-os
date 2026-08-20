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

        self.assertEqual(captured["body"]["model"], "openclaw/tony")
        self.assertEqual(captured["body"]["user"], "narratiive:tony:telegram")
        self.assertEqual(captured["body"]["input"], "What did they say?")
        self.assertEqual(
            {tool["name"] for tool in captured["body"]["tools"]},
            {"get_executive_brief", "get_current_leads", "get_open_work_status", "get_recent_execution_status"},
        )
        self.assertIn("current Narratiive state", captured["body"]["instructions"])
        self.assertIn("recent-execution status", captured["body"]["instructions"])
        headers = {key.casefold(): value for key, value in captured["headers"].items()}
        self.assertEqual(headers["x-openclaw-agent-id"], "tony")
        self.assertEqual(headers["x-openclaw-session-key"], "narratiive:tony:telegram")
        self.assertEqual(headers["authorization"], "Bearer secret")

    def test_independent_telegram_turns_share_the_same_openresponses_user(self):
        bodies = []

        def fake_urlopen(request, timeout):
            bodies.append(json.loads(request.data))
            return _Response({"output_text": "Understood."})

        gateway = TonyAgentGateway(
            TonyAgentGatewayConfig(session_key="narratiive:tony:telegram", user_id="matt:telegram")
        )
        with mock.patch("openclaw.tony_agent_gateway.urlopen", side_effect=fake_urlopen):
            gateway.converse("Jimmy replied yesterday.")
            gateway.converse("What did he say?")

        self.assertEqual(len(bodies), 2)
        self.assertEqual([body["user"] for body in bodies], ["matt:telegram", "matt:telegram"])
        self.assertNotIn("previous_response_id", bodies[0])
        self.assertNotIn("previous_response_id", bodies[1])

    def test_environment_defaults_openresponses_user_to_session_key(self):
        config = TonyAgentGatewayConfig.from_env({"TONY_OPENCLAW_SESSION_KEY": "agent:tony:telegram:matt"})
        self.assertEqual(config.session_key, "agent:tony:telegram:matt")
        self.assertEqual(config.user_id, "agent:tony:telegram:matt")

    def test_environment_can_isolate_openresponses_user_explicitly(self):
        config = TonyAgentGatewayConfig.from_env(
            {
                "TONY_OPENCLAW_SESSION_KEY": "agent:tony:telegram:matt",
                "TONY_OPENCLAW_USER_ID": "matt",
            }
        )
        self.assertEqual(config.user_id, "matt")

    def test_agent_can_ground_natural_language_in_executive_brief_tool(self):
        requests = []
        responses = iter(
            [
                {
                    "id": "resp-1",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "get_executive_brief",
                            "arguments": json.dumps({"period": "morning"}),
                        }
                    ],
                },
                {
                    "ok": True,
                    "reply": "Priority one is the live positive reply from Jimmy.",
                    "command": "morning",
                    "status": "attention",
                    "data": {"agency_state": {"executive_items": [{"company": "Jimmy Co"}]}},
                },
                {"id": "resp-2", "output_text": "Jimmy's positive reply is the first thing I'd handle today."},
            ]
        )

        def fake_urlopen(request, timeout):
            requests.append((request.full_url, json.loads(request.data), dict(request.header_items())))
            return _Response(next(responses))

        gateway = TonyAgentGateway(
            TonyAgentGatewayConfig(
                responses_url="http://openclaw/v1/responses",
                control_plane_url="http://tony/telegram/inbound",
                control_plane_token="bridge-secret",
                user_id="matt",
            )
        )
        with mock.patch("openclaw.tony_agent_gateway.urlopen", side_effect=fake_urlopen):
            reply = gateway.converse("Morning Tony, anything important?")

        self.assertEqual(reply, "Jimmy's positive reply is the first thing I'd handle today.")
        self.assertEqual([item[0] for item in requests], ["http://openclaw/v1/responses", "http://tony/telegram/inbound", "http://openclaw/v1/responses"])
        self.assertEqual(requests[0][1]["user"], "matt")
        self.assertEqual(requests[1][1], {"text": "/morning", "source": "openclaw_agent_tool"})
        control_headers = {key.casefold(): value for key, value in requests[1][2].items()}
        self.assertEqual(control_headers["authorization"], "Bearer bridge-secret")
        continuation = requests[2][1]
        self.assertEqual(continuation["user"], "matt")
        self.assertEqual(continuation["previous_response_id"], "resp-1")
        self.assertEqual(continuation["input"][0]["type"], "function_call_output")
        self.assertEqual(continuation["input"][0]["call_id"], "call-1")
        tool_output = json.loads(continuation["input"][0]["output"])
        self.assertEqual(tool_output["command"], "morning")
        self.assertIn("Jimmy", tool_output["reply"])

    def test_agent_can_read_current_leads_without_user_phrase_matching(self):
        captured = []

        def fake_post_json(url, body, *, headers, label):
            captured.append((url, body, label))
            return {"ok": True, "command": "leads", "reply": "Inbound leads — current: 1"}

        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with mock.patch.object(gateway, "_post_json", side_effect=fake_post_json):
            result = gateway._execute_tool("get_current_leads", {})

        self.assertTrue(result["ok"])
        self.assertEqual(captured[0][1]["text"], "/leads")
        self.assertEqual(captured[0][2], "Narratiive control plane")

    def test_agent_can_read_open_work_status_without_user_phrase_matching(self):
        captured = []

        def fake_post_json(url, body, *, headers, label):
            captured.append(body)
            return {"ok": True, "command": "agency_focus_action_status", "reply": "Research is still awaiting worker confirmation."}

        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with mock.patch.object(gateway, "_post_json", side_effect=fake_post_json):
            result = gateway._execute_tool("get_open_work_status", {})

        self.assertTrue(result["ok"])
        self.assertEqual(captured[0], {"text": "what's the status", "source": "openclaw_agent_tool"})

    def test_agent_can_verify_recent_execution_and_outcome_separately(self):
        captured = []

        def fake_post_json(url, body, *, headers, label):
            captured.append(body["text"])
            return {"ok": True, "command": "verified_execution_status", "reply": "Verified evidence exists."}

        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with mock.patch.object(gateway, "_post_json", side_effect=fake_post_json):
            execution = gateway._execute_tool("get_recent_execution_status", {"scope": "execution"})
            outcome = gateway._execute_tool("get_recent_execution_status", {"scope": "outcome"})

        self.assertTrue(execution["ok"])
        self.assertTrue(outcome["ok"])
        self.assertEqual(captured, ["did that happen", "did that work"])

    def test_recent_execution_tool_rejects_unknown_scope(self):
        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        result = gateway._execute_tool("get_recent_execution_status", {"scope": "something-else"})
        self.assertEqual(result, {"ok": False, "error": "scope must be execution or outcome"})

    def test_control_plane_failure_is_returned_as_evidence_not_invented_success(self):
        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with mock.patch.object(gateway, "_post_json", side_effect=TonyAgentGatewayError("bridge unavailable")):
            result = gateway._execute_tool("get_executive_brief", {"period": "morning"})
        self.assertEqual(result, {"ok": False, "error": "bridge unavailable"})

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
