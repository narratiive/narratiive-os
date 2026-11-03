from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.run_tony_agency_acceptance import (
    SANDBOX_MODEL,
    STAGE_WORKFLOWS,
    TONY_RESPONSE_MODEL,
    _has_external_effect,
    _sandbox_config,
    _sandbox_env,
    _send_turn,
)


class TonyAgencyAcceptanceRunnerTests(unittest.TestCase):
    def test_turn_routes_through_tony_while_sandbox_config_selects_local_model(self) -> None:
        response = mock.MagicMock()
        response.read.return_value = b'{"id":"response-1","output_text":"Ready"}'
        response.__enter__.return_value = response

        with mock.patch("scripts.run_tony_agency_acceptance.urlopen", return_value=response) as opener:
            turn = _send_turn("http://127.0.0.1:19001/v1/responses", "token", "session", "Assess it")

        request = opener.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], TONY_RESPONSE_MODEL)
        self.assertEqual(body["model"], "openclaw/tony")
        self.assertEqual(turn.response, "Ready")

    def test_negative_external_action_attestation_is_not_a_false_positive(self) -> None:
        self.assertFalse(_has_external_effect({"quality_gate": {"no_external_action_taken": True}, "external_action_taken": False}))

    def test_verified_external_action_is_detected(self) -> None:
        self.assertTrue(_has_external_effect({"receipt": {"external_action_taken": True}}))
        self.assertTrue(_has_external_effect({"event_type": "email_sent"}))

    def test_client_operations_uses_the_registered_discovery_preparation_workflow_id(self) -> None:
        self.assertIn("blueprint_lite_to_discovery_preparation", STAGE_WORKFLOWS["Client operations"])
        self.assertNotIn("blueprint_lite_to_discovery_prep", STAGE_WORKFLOWS["Client operations"])

    def test_sandbox_is_local_model_only_and_removes_hosted_provider_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _sandbox_config(root, 19001, "sandbox-token")
            self.assertEqual(config["auth"]["profiles"], {})
            self.assertEqual(config["agents"]["defaults"]["model"], SANDBOX_MODEL)
            self.assertTrue(all(agent["model"] == SANDBOX_MODEL for agent in config["agents"]["list"]))
            inherited = {
                "ANTHROPIC_API_KEY": "must-not-leak",
                "TONY_DISPATCH_GMAIL_URL": "https://provider.invalid/gmail",
                "TONY_DISPATCH_GMAIL_TOKEN": "must-not-leak",
                "TONY_DISPATCH_CLAUDE_API_KEY": "must-not-leak",
                "NARRATIIVE_RUNTIME_ROOT": "/production/runtime",
                "OPENAI_API_KEY": "must-not-leak",
                "OPENAI_BASE_URL": "https://provider.invalid/openai",
                "OLLAMA_API_KEY": "must-not-leak",
                "OLLAMA_HOST": "https://provider.invalid/ollama",
            }
            with mock.patch.dict("os.environ", inherited, clear=False):
                env = _sandbox_env(root, 19002, 19001, "sandbox-token", "bridge-token")
            self.assertEqual(env["TONY_DISPATCH_CLAUDE_MODE"], "")
            self.assertEqual(env["TONY_DISPATCH_CLAUDE_MODEL"], "")
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertNotIn("TONY_DISPATCH_GMAIL_URL", env)
            self.assertNotIn("TONY_DISPATCH_GMAIL_TOKEN", env)
            self.assertNotIn("TONY_DISPATCH_CLAUDE_API_KEY", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("OPENAI_BASE_URL", env)
            self.assertEqual(env["OLLAMA_API_KEY"], "narratiive-synthetic-local-only")
            self.assertEqual(env["OLLAMA_HOST"], "http://127.0.0.1:11434")
            self.assertEqual(env["TONY_HOSTED_MODEL_REQUEST_RESERVE_USD"], "0")
            self.assertEqual(Path(env["TONY_HOSTED_MODEL_USAGE_LEDGER"]).parent, root / "state")
            self.assertEqual(Path(env["NARRATIIVE_RUNTIME_ROOT"]), root / "state" / "runtime")
            self.assertEqual(Path(env["TONY_BRIEFING_DECISION_REGISTER_PATH"]).parent, root / "state")
            self.assertEqual(env["NARRATIIVE_GATEWAY_ENDPOINT"], "http://127.0.0.1:9/")
            self.assertEqual(env["NARRATIIVE_GATEWAY_HEALTH_ENDPOINT"], "http://127.0.0.1:9/health")


if __name__ == "__main__":
    unittest.main()
