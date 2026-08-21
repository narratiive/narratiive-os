from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIALISTS = ["research", "strategy", "creative-director", "production", "operations"]
CONSEQUENTIAL_TOOLS = {"message", "gateway", "cron", "nodes", "exec", "process"}
TONY_TOOLS = {
    "agents_list",
    "sessions_list",
    "sessions_history",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "session_status",
    "narratiive-control-plane",
}


class OpenClawFleetConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        self.agents = {agent["id"]: agent for agent in self.config["agents"]["list"]}

    def test_uses_stable_openclaw_agents_list_schema(self):
        self.assertNotIn("entries", self.config["agents"])
        self.assertNotIn("ownership", self.config["agents"])
        self.assertEqual(set(self.agents), {"tony", *SPECIALISTS})

    def test_tony_can_delegate_only_to_canonical_specialists(self):
        self.assertEqual(set(self.agents["tony"]["subagents"]["allowAgents"]), set(SPECIALISTS))
        self.assertTrue(self.agents["tony"]["subagents"]["requireAgentId"])
        self.assertEqual(self.agents["tony"]["subagents"]["delegationMode"], "prefer")
        self.assertIn("agents_list", self.agents["tony"]["tools"]["allow"])

    def test_tony_workspace_requires_runtime_agent_discovery_before_spawning(self):
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("call `agents_list`", contract)
        self.assertIn("Use the exact returned `agentId` in `sessions_spawn`", contract)
        self.assertIn("runtime configuration blocker", contract)

    def test_tony_heartbeat_is_bounded_proactive_and_only_tony_runs_it(self):
        heartbeat = self.agents["tony"]["heartbeat"]
        self.assertEqual(heartbeat["every"], "1h")
        self.assertEqual(heartbeat["target"], "last")
        self.assertFalse(heartbeat["lightContext"])
        self.assertFalse(heartbeat["isolatedSession"])
        self.assertEqual(heartbeat["activeHours"], {"start": "07:00", "end": "22:00", "timezone": "Europe/London"})
        prompt = heartbeat["prompt"]
        self.assertIn("proactive Chief of Staff", prompt)
        self.assertIn("stalled/failed/blocked", prompt)
        self.assertIn("HEARTBEAT_OK", prompt)
        self.assertIn("never claim external execution without returned Narratiive evidence", prompt)
        self.assertIn("narratiive_executive_brief", prompt)
        self.assertIn("narratiive_open_work_status", prompt)
        self.assertNotIn("heartbeat", self.config["agents"]["defaults"])
        for agent_id in SPECIALISTS:
            with self.subTest(agent_id=agent_id):
                self.assertNotIn("heartbeat", self.agents[agent_id])

    def test_tony_tool_surface_is_only_orchestration_and_narratiive_control_plane(self):
        allowed = set(self.agents["tony"]["tools"]["allow"])
        self.assertEqual(allowed, TONY_TOOLS)
        self.assertNotIn("read", allowed)
        self.assertNotIn("write", allowed)
        self.assertNotIn("edit", allowed)
        self.assertNotIn("browser", allowed)
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("direct tool surface is intentionally limited", contract)
        self.assertIn("bounded workspace research belongs with the specialist agents", contract)

    def test_heartbeat_has_native_read_only_control_plane_plugin_but_no_consequential_tools(self):
        allowed = set(self.agents["tony"]["tools"]["allow"])
        denied = set(self.agents["tony"]["tools"]["deny"])
        for required in {"agents_list", "sessions_list", "sessions_history", "sessions_yield", "subagents", "session_status"}:
            self.assertIn(required, allowed)
        self.assertIn("narratiive-control-plane", allowed)
        self.assertTrue({"exec", "process", "gateway", "cron", "nodes"}.issubset(denied))
        prompt = self.agents["tony"]["heartbeat"]["prompt"]
        self.assertIn("Do not send messages", prompt)
        self.assertIn("mutate Notion", prompt)

    def test_specialists_are_isolated_and_cannot_spawn_or_execute_consequential_actions(self):
        for agent_id in SPECIALISTS:
            with self.subTest(agent_id=agent_id):
                agent = self.agents[agent_id]
                self.assertEqual(agent["sandbox"]["mode"], "all")
                self.assertEqual(agent["sandbox"]["scope"], "agent")
                denied = set(agent["tools"]["deny"])
                self.assertIn("sessions_spawn", denied)
                self.assertTrue(CONSEQUENTIAL_TOOLS.issubset(denied))

    def test_operations_is_read_only_while_other_specialists_may_prepare_reversible_workspace_artifacts(self):
        self.assertEqual(self.agents["operations"]["sandbox"]["workspaceAccess"], "ro")
        self.assertEqual(self.agents["operations"]["tools"]["allow"], ["read"])
        for agent_id in ("research", "strategy", "creative-director", "production"):
            with self.subTest(agent_id=agent_id):
                self.assertEqual(self.agents[agent_id]["sandbox"]["workspaceAccess"], "rw")
                self.assertIn("write", self.agents[agent_id]["tools"]["allow"])

    def test_session_visibility_is_limited_to_tonys_spawn_tree_and_direct_messages_are_isolated(self):
        self.assertEqual(self.config["tools"]["sessions"]["visibility"], "tree")
        self.assertFalse(self.config["tools"]["agentToAgent"]["enabled"])
        self.assertEqual(self.config["session"]["scope"], "per-sender")
        self.assertEqual(self.config["session"]["dmScope"], "per-channel-peer")


if __name__ == "__main__":
    unittest.main()
