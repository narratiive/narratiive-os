from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.install_openclaw_fleet import CONTROL_PLANE_PLUGIN_ID, CONTROL_PLANE_PLUGIN_PATH, build_install_plan, install


class OpenClawFleetInstallTests(unittest.TestCase):
    def test_install_plan_preserves_unrelated_provider_channel_plugin_and_agent_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            existing = {
                "models": {"providers": {"ollama": {"baseUrl": "http://127.0.0.1:11434"}}},
                "channels": {"telegram": {"enabled": True}},
                "agents": {
                    "list": [
                        {"id": "tony", "model": "ollama/qwen3.5"},
                        {"id": "personal", "workspace": "~/.openclaw/workspace-personal"},
                    ]
                },
                "plugins": {"allow": ["existing-safe-plugin"], "load": {"paths": ["/tmp/existing-plugin"]}},
            }
            merged, workspace_files = build_install_plan(home, existing)

            self.assertEqual(merged["models"], existing["models"])
            self.assertEqual(merged["channels"], existing["channels"])
            self.assertNotIn("entries", merged["agents"])
            self.assertNotIn("ownership", merged["agents"])
            agents = {agent["id"]: agent for agent in merged["agents"]["list"]}
            self.assertEqual(agents["tony"]["model"], "ollama/qwen3.5")
            self.assertEqual(
                set(agents["tony"]["subagents"]["allowAgents"]),
                {"research", "strategy", "creative-director", "production", "operations"},
            )
            self.assertEqual(agents["personal"]["workspace"], "~/.openclaw/workspace-personal")
            self.assertEqual(set(merged["plugins"]["allow"]), {"existing-safe-plugin", CONTROL_PLANE_PLUGIN_ID})
            self.assertIn("/tmp/existing-plugin", merged["plugins"]["load"]["paths"])
            self.assertIn(str(CONTROL_PLANE_PLUGIN_PATH), merged["plugins"]["load"]["paths"])
            self.assertTrue(merged["plugins"]["entries"][CONTROL_PLANE_PLUGIN_ID]["enabled"])
            for filename in ("AGENTS.md", "IDENTITY.md", "USER.md", "SOUL.md"):
                self.assertIn(home / ".openclaw" / "workspace-tony" / filename, workspace_files)
            self.assertIn(home / ".openclaw" / "workspace-research" / "AGENTS.md", workspace_files)

    def test_dry_run_does_not_mutate_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = install(home=home, apply=False)
            self.assertFalse((home / ".openclaw").exists())
            self.assertFalse(result["apply"])
            self.assertEqual(result["control_plane_plugin_path"], str(CONTROL_PLANE_PLUGIN_PATH))

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
            self.assertTrue(written["plugins"]["entries"][CONTROL_PLANE_PLUGIN_ID]["enabled"])
            self.assertIn(str(CONTROL_PLANE_PLUGIN_PATH), written["plugins"]["load"]["paths"])
            self.assertTrue((config_dir / "openclaw.json.narratiive-backup").exists())
            self.assertEqual(
                {agent["id"] for agent in written["agents"]["list"]},
                {"tony", "research", "strategy", "creative-director", "production", "operations"},
            )

            tony = (config_dir / "workspace-tony" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("sessions_list", tony)
            self.assertIn("sessions_history", tony)
            self.assertIn("sessions_yield", tony)
            self.assertIn("Do not infer completion from elapsed time", tony)

            identity = (config_dir / "workspace-tony" / "IDENTITY.md").read_text(encoding="utf-8")
            user = (config_dir / "workspace-tony" / "USER.md").read_text(encoding="utf-8")
            soul = (config_dir / "workspace-tony" / "SOUL.md").read_text(encoding="utf-8")
            self.assertIn("single conversational interface", identity)
            self.assertIn("not a generic chatbot", identity)
            self.assertIn("Matt is the founder", user)
            self.assertIn("OpenClaw for conversation", soul)

            for agent_id in ("research", "strategy", "creative-director", "production", "operations"):
                content = (config_dir / f"workspace-{agent_id}" / "AGENTS.md").read_text(encoding="utf-8")
                self.assertIn("bounded specialist", content)
                self.assertIn("does not mean an external action occurred", content)

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
