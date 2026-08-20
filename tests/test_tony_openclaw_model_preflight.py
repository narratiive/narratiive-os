from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_tony_openclaw_live import (
    EXPECTED_AGENT_IDS,
    build_report,
    configured_primary_model,
    is_explicit_provider_model,
)


class TonyOpenClawModelPreflightTests(unittest.TestCase):
    def test_resolves_tony_model_before_shared_default(self) -> None:
        config = {
            "agents": {
                "defaults": {"model": {"primary": "anthropic/claude-sonnet-4-6"}},
                "list": [
                    {"id": "tony", "model": {"primary": "openai/gpt-5.5"}},
                    {"id": "research"},
                ],
            }
        }
        self.assertEqual(
            configured_primary_model(config),
            ("openai/gpt-5.5", "agents.list[tony].model"),
        )

    def test_resolves_shared_default_when_tony_has_no_override(self) -> None:
        config = {
            "agents": {
                "defaults": {"model": {"primary": "anthropic/claude-sonnet-4-6"}},
                "list": [{"id": "tony"}],
            }
        }
        self.assertEqual(
            configured_primary_model(config),
            ("anthropic/claude-sonnet-4-6", "agents.defaults.model"),
        )

    def test_requires_provider_model_not_alias_or_bare_model(self) -> None:
        self.assertTrue(is_explicit_provider_model("ollama/qwen3.5:latest"))
        self.assertTrue(is_explicit_provider_model("anthropic/claude-sonnet-4-6"))
        self.assertFalse(is_explicit_provider_model("qwen3.5:latest"))
        self.assertFalse(is_explicit_provider_model("fast"))
        self.assertFalse(is_explicit_provider_model(""))

    def test_live_acceptance_fails_fast_before_agent_post_when_model_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "openclaw.json"
            config_path.write_text(
                json.dumps({"agents": {"list": [{"id": agent_id} for agent_id in EXPECTED_AGENT_IDS]}}),
                encoding="utf-8",
            )
            post_calls: list[dict[str, object]] = []

            def transport(url, body=None, *, headers=None, timeout=0):
                if body is None:
                    return {"models": [{"name": "qwen3.5:latest"}]}
                post_calls.append(body)
                raise AssertionError("live OpenClaw POST must not run without explicit provider/model")

            report = build_report(
                config_path=config_path,
                responses_url="http://openclaw/v1/responses",
                agent_id="tony",
                session_key="session",
                gateway_token="token",
                ollama_tags_url="http://ollama/api/tags",
                live=True,
                transport=transport,
                agent_inventory=lambda: list(EXPECTED_AGENT_IDS),
            )

            self.assertFalse(report["model_selection_ready"])
            self.assertIsNone(report["configured_primary_model"])
            self.assertFalse(report["live_passed"])
            self.assertEqual(report["scenarios"], [])
            self.assertIn("explicit provider/model", report["live_error"])
            self.assertEqual(post_calls, [])


if __name__ == "__main__":
    unittest.main()
