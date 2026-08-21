from __future__ import annotations

import unittest
from pathlib import Path

from openclaw.tony_agent_gateway import TonyAgentGateway


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "index.js"
LIVE_BRIDGE = ROOT / "openclaw" / "tony_live_bridge.py"


class OpenClawControlPlaneNoRecursionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin_source = PLUGIN.read_text(encoding="utf-8")
        self.bridge_source = LIVE_BRIDGE.read_text(encoding="utf-8")

    def test_native_control_plane_reads_stay_on_deterministic_slash_surface(self):
        expected_commands = (
            "/morning",
            "/evening",
            "/leads",
            "/what's the status",
            "/did that happen",
            "/did that work",
        )
        for command in expected_commands:
            with self.subTest(command=command):
                self.assertTrue(TonyAgentGateway.is_system_command(command))

        self.assertIn('return "/what\'s the status";', self.plugin_source)
        self.assertIn('? "/did that happen" : "/did that work";', self.plugin_source)
        self.assertNotIn('return "what\'s the status";', self.plugin_source)
        self.assertNotIn('? "did that happen" : "did that work";', self.plugin_source)

    def test_plugin_calls_cannot_reenter_the_openclaw_conversation_branch(self):
        self.assertIn('source: "openclaw_native_tool"', self.plugin_source)
        self.assertIn('if TonyAgentGateway.is_system_command(text):', self.bridge_source)
        self.assertIn('status, payload = self.base._handle_telegram_command(text)', self.bridge_source)
        self.assertIn('reply = self.agent_gateway.converse(text)', self.bridge_source)
        self.assertIn(
            "never routes a native tool call back into OpenClaw",
            self.plugin_source,
        )


if __name__ == "__main__":
    unittest.main()
