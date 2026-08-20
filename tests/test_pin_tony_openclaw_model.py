from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.diagnose_tony_openclaw_model import runtime_model_status
from scripts.pin_tony_openclaw_model import (
    build_plan,
    is_explicit_model_ref,
    pin_model,
    resolved_runtime_model,
)


class TonyOpenClawModelPinTests(unittest.TestCase):
    def test_runtime_diagnostic_targets_tony_agent(self) -> None:
        completed = mock.Mock(returncode=0, stdout=json.dumps({"resolvedModel": "anthropic/claude-sonnet-4-6"}), stderr="")
        with mock.patch("scripts.diagnose_tony_openclaw_model.subprocess.run", return_value=completed) as run:
            report = runtime_model_status("tony")
        self.assertTrue(report["available"])
        self.assertEqual(report["agent_id"], "tony")
        self.assertEqual(
            run.call_args.args[0],
            ["openclaw", "models", "status", "--agent", "tony", "--json"],
        )

    def test_resolved_runtime_model_requires_explicit_provider_model(self) -> None:
        completed = mock.Mock(returncode=0, stdout=json.dumps({"resolvedModel": "anthropic/claude-sonnet-4-6"}), stderr="")
        with mock.patch("scripts.pin_tony_openclaw_model.subprocess.run", return_value=completed) as run:
            model, source = resolved_runtime_model("tony")
        self.assertEqual(model, "anthropic/claude-sonnet-4-6")
        self.assertIn("--agent tony", source)
        self.assertEqual(
            run.call_args.args[0],
            ["openclaw", "models", "status", "--agent", "tony", "--json"],
        )

    def test_resolved_runtime_model_refuses_alias_or_guess(self) -> None:
        completed = mock.Mock(returncode=0, stdout=json.dumps({"resolvedModel": "sonnet"}), stderr="")
        with mock.patch("scripts.pin_tony_openclaw_model.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "refusing to guess"):
                resolved_runtime_model("tony")

    def test_pin_uses_shared_default_when_tony_has_no_model_override(self) -> None:
        config = {"agents": {"defaults": {"subagents": {"maxConcurrent": 4}}, "list": [{"id": "tony"}, {"id": "research"}]}}
        updated, target = pin_model(config, "anthropic/claude-sonnet-4-6")
        self.assertEqual(target, "agents.defaults.model.primary")
        self.assertEqual(updated["agents"]["defaults"]["model"]["primary"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(updated["agents"]["defaults"]["subagents"]["maxConcurrent"], 4)
        self.assertNotIn("model", config["agents"]["defaults"])

    def test_pin_replaces_existing_tony_alias_without_changing_fleet_default(self) -> None:
        config = {
            "agents": {
                "defaults": {"model": {"primary": "openai/gpt-5.5"}},
                "list": [{"id": "tony", "model": "sonnet"}, {"id": "research"}],
            }
        }
        updated, target = pin_model(config, "anthropic/claude-sonnet-4-6")
        self.assertEqual(target, "agents.list[tony].model.primary")
        self.assertEqual(updated["agents"]["list"][0]["model"]["primary"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(updated["agents"]["defaults"]["model"]["primary"], "openai/gpt-5.5")

    def test_build_plan_is_noop_when_tony_is_already_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "openclaw.json"
            config_path.write_text(
                json.dumps({"agents": {"list": [{"id": "tony", "model": {"primary": "anthropic/claude-sonnet-4-6"}}]}}),
                encoding="utf-8",
            )
            with mock.patch("scripts.pin_tony_openclaw_model.resolved_runtime_model") as runtime:
                plan, updated = build_plan(config_path)
        runtime.assert_not_called()
        self.assertEqual(plan["action"], "none")
        self.assertIsNone(updated)

    def test_explicit_model_ref_validation(self) -> None:
        self.assertTrue(is_explicit_model_ref("ollama/qwen3.5:latest"))
        self.assertTrue(is_explicit_model_ref("openrouter/anthropic/claude-sonnet-4-6"))
        self.assertFalse(is_explicit_model_ref("qwen3.5:latest"))
        self.assertFalse(is_explicit_model_ref(""))
        self.assertFalse(is_explicit_model_ref("anthropic/claude sonnet"))


if __name__ == "__main__":
    unittest.main()
