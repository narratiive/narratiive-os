from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
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
    @staticmethod
    def _write_work_session(state_dir: Path, session_key: str, entries: list[dict]) -> Path:
        sessions_dir = state_dir / "agents" / "tony" / "sessions"
        sessions_dir.mkdir(parents=True)
        transcript = sessions_dir / "session-1.jsonl"
        transcript.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        (sessions_dir / "sessions.json").write_text(
            json.dumps({f"agent:tony:{session_key}": {"sessionId": "session-1", "sessionFile": str(transcript)}}),
            encoding="utf-8",
        )
        return transcript

    def test_only_explicit_slash_commands_use_deterministic_surface(self):
        self.assertTrue(TonyAgentGateway.is_system_command("/health"))
        self.assertTrue(TonyAgentGateway.is_system_command("  /diagnostics"))
        self.assertFalse(TonyAgentGateway.is_system_command("Morning Tony, anything important?"))
        self.assertFalse(TonyAgentGateway.is_system_command("Tony - what should I be working on today?"))
        self.assertFalse(TonyAgentGateway.is_system_command("whta shoudl I focus on today?"))
        self.assertFalse(TonyAgentGateway.is_system_command("sort that out"))
        self.assertFalse(TonyAgentGateway.is_system_command("how is the research agent getting on?"))

    def test_gateway_is_thin_and_leaves_prompt_and_tool_loop_to_native_openclaw_agent(self):
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

        body = captured["body"]
        self.assertEqual(body["model"], "openclaw/tony")
        self.assertEqual(body["user"], "narratiive:tony:telegram")
        self.assertEqual(body["input"], "What did they say?")
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)
        self.assertNotIn("previous_response_id", body)
        self.assertNotIn("instructions", body)
        headers = {key.casefold(): value for key, value in captured["headers"].items()}
        self.assertEqual(headers["x-openclaw-agent-id"], "tony")
        self.assertEqual(headers["x-openclaw-session-key"], "narratiive:tony:telegram")
        self.assertEqual(headers["x-openclaw-message-channel"], "telegram")
        self.assertEqual(headers["authorization"], "Bearer secret")

    def test_workspace_bootstrap_is_the_single_tony_behaviour_contract(self):
        agents_path = Path(__file__).resolve().parents[1] / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md"
        contract = agents_path.read_text(encoding="utf-8")
        self.assertIn("Speak naturally and interpret ordinary English, including typos", contract)
        self.assertIn("Use Narratiive OS read tools whenever a claim depends on current business state", contract)
        self.assertIn("Never claim that an external action happened unless the control plane returns decision-grade evidence", contract)
        self.assertIn("You orchestrate five specialists", contract)
        self.assertIn("Do not make Matt restate a magic approval phrase", contract)
        self.assertIn("the Telegram ingress has already acknowledged the commission", contract)
        self.assertIn("Complete the explicitly requested safe milestone before returning", contract)
        self.assertIn("use `sessions_yield` when its result is required", contract)

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
        self.assertTrue(all("tools" not in body for body in bodies))
        self.assertTrue(all("instructions" not in body for body in bodies))
        self.assertTrue(all("previous_response_id" not in body for body in bodies))

    def test_durable_work_uses_isolated_session_and_worker_deadline(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["headers"] = {key.casefold(): value for key, value in request.header_items()}
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return _Response({"output_text": "Completed work"})

        gateway = TonyAgentGateway(
            TonyAgentGatewayConfig(
                session_key="narratiive:tony:telegram",
                timeout_seconds=120,
                work_timeout_seconds=900,
            )
        )
        with mock.patch("openclaw.tony_agent_gateway.urlopen", side_effect=fake_urlopen):
            reply = gateway.converse_for_work("Research this", "telegram-abc")

        self.assertEqual(reply, "Completed work")
        self.assertEqual(captured["timeout"], 900)
        self.assertEqual(captured["body"]["user"], "narratiive:tony:telegram:work:telegram-abc")
        self.assertEqual(
            captured["headers"]["x-openclaw-session-key"],
            "narratiive:tony:telegram:work:telegram-abc",
        )

    def test_durable_work_waits_for_tony_after_sessions_yield(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            session_key = "narratiive:tony:telegram:work:telegram-abc"
            transcript = self._write_work_session(
                state_dir,
                session_key,
                [
                    {
                        "timestamp": "2026-09-11T12:00:00Z",
                        "message": {
                            "role": "assistant",
                            "stopReason": "toolUse",
                            "content": [{"type": "toolCall", "name": "sessions_yield"}],
                        },
                    }
                ],
            )

            def finish_after_yield():
                time.sleep(0.03)
                with transcript.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "timestamp": "2026-09-11T12:02:00Z",
                                "message": {
                                    "role": "assistant",
                                    "stopReason": "stop",
                                    "content": [{"type": "text", "text": "Verified company and rationale"}],
                                },
                            }
                        )
                        + "\n"
                    )

            gateway = TonyAgentGateway(
                TonyAgentGatewayConfig(state_dir=state_dir, work_timeout_seconds=1, work_poll_seconds=0.01)
            )
            thread = threading.Thread(target=finish_after_yield)
            thread.start()
            with mock.patch(
                "openclaw.tony_agent_gateway.urlopen",
                return_value=_Response({"output_text": "transient sub-agent notice"}),
            ):
                reply = gateway.converse_for_work("Research this", "telegram-abc")
            thread.join()
            self.assertEqual(reply, "Verified company and rationale")

    def test_restart_recovers_resumed_result_without_duplicate_openclaw_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            session_key = "narratiive:tony:telegram:work:telegram-abc"
            self._write_work_session(
                state_dir,
                session_key,
                [
                    {
                        "timestamp": "2026-09-11T12:00:00Z",
                        "message": {
                            "role": "assistant",
                            "stopReason": "toolUse",
                            "content": [{"type": "toolCall", "name": "sessions_yield"}],
                        },
                    },
                    {
                        "timestamp": "2026-09-11T12:02:00Z",
                        "message": {
                            "role": "assistant",
                            "stopReason": "stop",
                            "content": [{"type": "text", "text": "Recovered final result"}],
                        },
                    },
                ],
            )
            gateway = TonyAgentGateway(TonyAgentGatewayConfig(state_dir=state_dir))
            with mock.patch("openclaw.tony_agent_gateway.urlopen") as request:
                reply = gateway.converse_for_work("Research this", "telegram-abc")
            self.assertEqual(reply, "Recovered final result")
            request.assert_not_called()

    def test_research_and_strategy_specialists_use_claude(self):
        fleet_path = Path(__file__).resolve().parents[1] / "openclaw" / "openclaw.fleet.json"
        fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
        models = {agent["id"]: agent.get("model") for agent in fleet["agents"]["list"]}
        self.assertEqual(models["research"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(models["strategy"], "anthropic/claude-sonnet-4-6")

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

    def test_gateway_no_longer_contains_client_tool_or_legacy_command_translation_surface(self):
        self.assertFalse(hasattr(TonyAgentGateway, "_TOOLS"))
        self.assertFalse(hasattr(TonyAgentGateway, "_execute_tool"))
        self.assertFalse(hasattr(TonyAgentGateway, "_extract_tool_calls"))
        fields = TonyAgentGatewayConfig.__dataclass_fields__
        self.assertNotIn("control_plane_url", fields)
        self.assertNotIn("control_plane_token", fields)
        self.assertNotIn("max_tool_rounds", fields)

    def test_acceptance_language_never_requires_phrase_matching(self):
        messages = (
            "Morning Tony, anything important?",
            "Tony - what should I be working on today?",
            "whta shoudl I focus on today?",
            "What did they say?",
            "sort that out",
            "use Thursday",
            "send it",
            "did it go?",
            "how is the research agent getting on?",
            "how is the strategy agent?",
            "how is the creative director getting on?",
            "what is production working on?",
        )
        for text in messages:
            with self.subTest(text=text):
                self.assertFalse(TonyAgentGateway.is_system_command(text))

    def test_openclaw_without_text_fails_closed_instead_of_guessing(self):
        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with mock.patch("openclaw.tony_agent_gateway.urlopen", return_value=_Response({"output": []})):
            with self.assertRaisesRegex(TonyAgentGatewayError, "no conversational response"):
                gateway.converse("Morning Tony")

    def test_slash_command_cannot_be_sent_to_agent_gateway(self):
        gateway = TonyAgentGateway(TonyAgentGatewayConfig())
        with self.assertRaisesRegex(TonyAgentGatewayError, "slash commands"):
            gateway.converse("/health")


if __name__ == "__main__":
    unittest.main()
