from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIALISTS = ["research", "strategy", "creative-director", "production", "operations"]
CONSEQUENTIAL_TOOLS = {"message", "gateway", "cron", "nodes", "exec", "process"}


class OpenClawFleetConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        self.entries = self.config["agents"]["entries"]

    def test_tony_can_delegate_only_to_canonical_specialists(self):
        self.assertEqual(self.config["agents"]["ownership"], "explicit")
        self.assertEqual(set(self.entries["tony"]["subagents"]["allowAgents"]), set(SPECIALISTS))
        self.assertTrue(self.entries["tony"]["subagents"]["requireAgentId"])
        self.assertEqual(self.entries["tony"]["subagents"]["delegationMode"], "prefer")

    def test_specialists_are_isolated_and_cannot_spawn_or_execute_consequential_actions(self):
        for agent_id in SPECIALISTS:
            with self.subTest(agent_id=agent_id):
                agent = self.entries[agent_id]
                self.assertEqual(agent["sandbox"]["mode"], "all")
                self.assertEqual(agent["sandbox"]["scope"], "agent")
                denied = set(agent["tools"]["deny"])
                self.assertIn("sessions_spawn", denied)
                self.assertTrue(CONSEQUENTIAL_TOOLS.issubset(denied))

    def test_operations_is_read_only_while_other_specialists_may_prepare_reversible_workspace_artifacts(self):
        self.assertEqual(self.entries["operations"]["sandbox"]["workspaceAccess"], "ro")
        self.assertEqual(self.entries["operations"]["tools"]["allow"], ["read"])
        for agent_id in ("research", "strategy", "creative-director", "production"):
            with self.subTest(agent_id=agent_id):
                self.assertEqual(self.entries[agent_id]["sandbox"]["workspaceAccess"], "rw")
                self.assertIn("write", self.entries[agent_id]["tools"]["allow"])

    def test_session_visibility_is_limited_to_tonys_spawn_tree_and_direct_messages_are_isolated(self):
        self.assertEqual(self.config["tools"]["sessions"]["visibility"], "tree")
        self.assertFalse(self.config["tools"]["agentToAgent"]["enabled"])
        self.assertEqual(self.config["session"]["scope"], "per-sender")
        self.assertEqual(self.config["session"]["dmScope"], "per-channel-peer")


if __name__ == "__main__":
    unittest.main()
