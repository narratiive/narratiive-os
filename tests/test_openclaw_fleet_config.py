from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIALISTS = ["research", "strategy", "creative-director", "production", "operations"]
CONSEQUENTIAL_TOOLS = {"message", "gateway", "cron", "nodes", "exec", "process"}
TONY_PROFILE_ADDITIONS = {
    "agents_list",
    "sessions_send",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "narratiive_read_state",
    "narratiive_execute_safe_read",
    "narratiive_request_action_approval",
    "narratiive_workflow_control",
}
LEGACY_STATE_TOOLS = {
    "narratiive_executive_brief",
    "narratiive_current_leads",
    "narratiive_open_work_status",
    "narratiive_recent_execution_status",
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
        self.assertIn("agents_list", self.agents["tony"]["tools"]["alsoAllow"])

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
        self.assertTrue(heartbeat["isolatedSession"])
        self.assertEqual(heartbeat["activeHours"], {"start": "07:00", "end": "22:00", "timezone": "Europe/London"})
        prompt = heartbeat["prompt"]
        self.assertIn("proactive Chief of Staff", prompt)
        self.assertIn("sessions_list", prompt)
        self.assertIn("persistent OpenClaw specialist assignments", prompt)
        self.assertIn("subagents", prompt)
        self.assertIn("stalled/failed/blocked", prompt)
        self.assertIn("HEARTBEAT_OK", prompt)
        self.assertIn("never claim external execution without returned Narratiive evidence", prompt)
        self.assertIn("Never infer status from old chat memory", prompt)
        self.assertIn("narratiive_read_state", prompt)
        self.assertIn("view executive_brief", prompt)
        self.assertIn("view open_work", prompt)
        self.assertTrue(all(tool not in prompt for tool in LEGACY_STATE_TOOLS))
        self.assertNotIn("heartbeat", self.config["agents"]["defaults"])
        for agent_id in SPECIALISTS:
            with self.subTest(agent_id=agent_id):
                self.assertNotIn("heartbeat", self.agents[agent_id])

    def test_tony_tool_surface_is_only_orchestration_and_narratiive_control_plane(self):
        tools = self.agents["tony"]["tools"]
        additions = set(tools["alsoAllow"])
        denied = set(tools["deny"])
        self.assertNotIn("allow", tools)
        self.assertEqual(additions, TONY_PROFILE_ADDITIONS)
        self.assertNotIn("sessions_list", denied)
        self.assertNotIn("sessions_send", denied)
        self.assertTrue({"session_status", "message"}.issubset(denied))
        self.assertTrue({"read", "write", "edit", "browser"}.isdisjoint(additions))
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("direct tool surface is intentionally limited", contract)
        self.assertIn("bounded workspace research belongs with the specialist agents", contract)

    def test_heartbeat_has_native_read_only_control_plane_plugin_but_no_consequential_tools(self):
        additions = set(self.agents["tony"]["tools"]["alsoAllow"])
        denied = set(self.agents["tony"]["tools"]["deny"])
        for required in {"agents_list", "sessions_yield", "subagents"}:
            self.assertIn(required, additions)
        self.assertNotIn("sessions_list", denied)
        self.assertIn("session_status", denied)
        self.assertTrue({"exec", "process", "gateway", "cron", "nodes"}.issubset(denied))
        prompt = self.agents["tony"]["heartbeat"]["prompt"]
        self.assertIn("Do not send messages", prompt)
        self.assertIn("mutate Notion", prompt)

    def test_specialist_status_combines_persistent_sessions_with_current_tree_activity(self):
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("`agents_list` is the authoritative discovery view", contract)
        self.assertIn("`subagents` is the live/recent task ledger", contract)
        self.assertIn("`sessions_list` is the durable discovery view", contract)
        self.assertIn("across Telegram resets, restarts, isolated heartbeat sessions", contract)
        self.assertIn("category `Narratiive specialists`", contract)
        self.assertIn("bounded transcript with `sessions_history`", contract)
        self.assertIn("no child job currently running", contract)

    def test_tony_can_steer_only_discovered_persistent_specialist_assignments(self):
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("continue the existing persistent specialist session instead of spawning a duplicate", contract)
        self.assertIn("use `sessions_send` with that exact discovered `sessionKey`", contract)
        self.assertIn("Do not use `sessions_send` to arbitrary sessions", contract)
        self.assertIn("do not target a specialist's generic main session", contract)
        self.assertIn("internal specialist instruction was handed off", contract)
        self.assertIn("never evidence of an external business consequence", contract)
        self.assertIn("sessions_send", self.agents["tony"]["tools"]["alsoAllow"])
        self.assertNotIn("sessions_send", self.agents["tony"]["tools"]["deny"])

    def test_broad_status_combines_business_state_with_roster_persistent_sessions_and_child_runs(self):
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("configured roster, persistent visible specialist assignments, current-tree child-job ledger", contract)
        self.assertIn("read `executive_brief`, `open_work` and `current_leads`", contract)
        self.assertIn("Open work is wider than spawned child jobs or visible specialist sessions", contract)
        self.assertIn("before asking Matt for outreach targets, goals, contacts, leads", contract)

    def test_tony_has_bounded_cross_session_visibility_only_for_canonical_specialists(self):
        self.assertEqual(self.config["tools"]["sessions"]["visibility"], "all")
        self.assertNotIn("sessions", self.agents["tony"]["tools"])
        agent_to_agent = self.config["tools"]["agentToAgent"]
        self.assertTrue(agent_to_agent["enabled"])
        self.assertEqual(set(agent_to_agent["allow"]), set(SPECIALISTS))
        self.assertEqual(self.config["session"]["scope"], "per-sender")
        self.assertEqual(self.config["session"]["dmScope"], "per-channel-peer")

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


if __name__ == "__main__":
    unittest.main()
