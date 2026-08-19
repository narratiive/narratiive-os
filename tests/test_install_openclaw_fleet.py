from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.install_openclaw_fleet import build_install_plan, install


class OpenClawFleetInstallTests(unittest.TestCase):
    def test_install_plan_preserves_unrelated_provider_and_channel_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            existing = {
                "models": {"providers": {"ollama": {"baseUrl": "http://127.0.0.1:11434"}}},
                "channels": {"telegram": {"enabled": True}},
                "agents": {"entries": {"tony": {"model": "ollama/qwen3.5"}}},
            }
            merged, workspace_files = build_install_plan(home, existing)

            self.assertEqual(merged["models"], existing["models"])
            self.assertEqual(merged["channels"], existing["channels"])
            self.assertEqual(merged["agents"]["entries"]["tony"]["model"], "ollama/qwen3.5")
            self.assertEqual(
                set(merged["agents"]["entries"]["tony"]["subagents"]["allowAgents"]),
                {"research", "strategy", "creative-director", "production", "operations"},
            )
            self.assertIn(home / ".openclaw" / "workspace-tony" / "AGENTS.md", workspace_files)
            self.assertIn(home / ".openclaw" / "workspace-research" / "AGENTS.md", workspace_files)

    def test_dry_run_does_not_mutate_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = install(home=home, apply=False)
            self.assertFalse((home / ".openclaw").exists())
            self.assertFalse(result["apply"])

    def test_apply_backs_up_existing_config_and_writes_tony_and_specialists(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config_dir = home / ".openclaw"
            config_dir.mkdir()
            config_path = config_dir / "openclaw.json"
            original = {
                "models": {"providers": {"ollama": {"baseUrl": "http://127.0.0.1:11434"}}},
                "channels": {"telegram": {"enabled": True}},
            }
            config_path.write_text(json.dumps(original), encoding="utf-8")

            result = install(home=home, apply=True)
            written = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertTrue(result["apply"])
            self.assertEqual(written["models"], original["models"])
            self.assertEqual(written["channels"], original["channels"])
            self.assertEqual(written["tools"]["sessions"]["visibility"], "tree")
            self.assertTrue((config_dir / "openclaw.json.narratiive-backup").exists())

            tony = (config_dir / "workspace-tony" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("sessions_list", tony)
            self.assertIn("sessions_history", tony)
            self.assertIn("sessions_yield", tony)
            self.assertIn("Do not infer completion from elapsed time", tony)

            for agent_id in ("research", "strategy", "creative-director", "production", "operations"):
                content = (config_dir / f"workspace-{agent_id}" / "AGENTS.md").read_text(encoding="utf-8")
                self.assertIn("bounded specialist", content)
                self.assertIn("do not mean an external action occurred", content)

    def test_tony_workspace_contract_supports_plain_english_status_and_followups(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            install(home=home, apply=True)
            tony = (home / ".openclaw" / "workspace-tony" / "AGENTS.md").read_text(encoding="utf-8")
            for phrase in ("What did they say?", "sort that out", "use Thursday", "send it", "did it go?"):
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, tony)
            self.assertIn("When Matt asks how a specialist is getting on", tony)
            self.assertIn("inspect live OpenClaw session state first", tony)


if __name__ == "__main__":
    unittest.main()
