from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_tony_openclaw_live import SCENARIOS, run_live_probe


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TONY_TOOLS = {
    "agents_list",
    "sessions_list",
    "sessions_history",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "session_status",
    "narratiive-control-plane",
}
EXPECTED_CONTROL_PLANE_TOOLS = {
    "narratiive_read_state",
    "narratiive_execute_safe_read",
    "narratiive_request_action_approval",
}
LEGACY_STATE_TOOLS = {
    "narratiive_executive_brief",
    "narratiive_current_leads",
    "narratiive_open_work_status",
    "narratiive_recent_execution_status",
}


class TonyChiefOfStaffToolSurfaceAcceptanceTests(unittest.TestCase):
    def test_plain_english_acceptance_still_enters_openclaw_without_client_tools(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            index = len(calls)
            text = (
                "Research completed its read-only mission inspection."
                if index in {3, 4}
                else f"natural Chief of Staff reply {index}"
            )
            return {"id": f"resp-{index}", "output_text": text}

        results = run_live_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="chief-of-staff-acceptance",
            gateway_token="token",
            transport=transport,
        )

        self.assertEqual(len(results), len(SCENARIOS))
        self.assertTrue(all(result["passed"] for result in results))
        self.assertTrue(all("tools" not in body for _, body, _, _ in calls))
        self.assertTrue(all("tool_choice" not in body for _, body, _, _ in calls))
        self.assertTrue(all("instructions" not in body for _, body, _, _ in calls))
        self.assertTrue(all(headers["x-openclaw-agent-id"] == "tony" for _, _, headers, _ in calls))

    def test_openclaw_owns_a_small_tony_tool_surface_while_specialists_keep_workspace_tools(self) -> None:
        config = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        agents = {agent["id"]: agent for agent in config["agents"]["list"]}
        self.assertEqual(set(agents["tony"]["tools"]["allow"]), EXPECTED_TONY_TOOLS)
        self.assertNotIn("read", agents["tony"]["tools"]["allow"])
        self.assertIn("read", agents["research"]["tools"]["allow"])
        self.assertIn("write", agents["research"]["tools"]["allow"])
        self.assertIn("read", agents["operations"]["tools"]["allow"])

    def test_control_plane_contract_is_three_stable_capability_tools(self) -> None:
        manifest = json.loads(
            (ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "openclaw.plugin.json").read_text(encoding="utf-8")
        )
        tools = set(manifest["contracts"]["tools"])
        self.assertEqual(tools, EXPECTED_CONTROL_PLANE_TOOLS)
        self.assertTrue(LEGACY_STATE_TOOLS.isdisjoint(tools))
        self.assertNotIn("narratiive_propose_action", tools)

        source = (ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "index.js").read_text(encoding="utf-8")
        self.assertIn('name: "narratiive_read_state"', source)
        self.assertIn('["executive_brief", "current_leads", "open_work", "recent_execution"]', source)
        for legacy_tool in LEGACY_STATE_TOOLS:
            self.assertNotIn(f'"{legacy_tool}"', source)

    def test_workspace_and_heartbeat_use_consolidated_state_view_without_phrase_routing(self) -> None:
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("narratiive_read_state", prompt)
        self.assertIn("executive_brief", prompt)
        self.assertIn("current_leads", prompt)
        self.assertIn("open_work", prompt)
        self.assertIn("recent_execution", prompt)
        self.assertIn("For a verified read-only inspection", prompt)
        self.assertIn("For reversible internal preparation", prompt)
        self.assertIn("For any external or persisted write", prompt)
        self.assertIn("native single-use approval gate", prompt)
        self.assertIn("execution_truth", prompt)
        self.assertIn("contextual turns, not commands to phrase-match", prompt)

        fleet = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        agents = {agent["id"]: agent for agent in fleet["agents"]["list"]}
        heartbeat = agents["tony"]["heartbeat"]["prompt"]
        self.assertIn("narratiive_read_state", heartbeat)
        self.assertTrue(all(tool not in heartbeat for tool in LEGACY_STATE_TOOLS))
        self.assertIn("view executive_brief", heartbeat)
        self.assertIn("view open_work", heartbeat)
        self.assertIn("view current_leads", heartbeat)
        self.assertIn("view recent_execution", heartbeat)


if __name__ == "__main__":
    unittest.main()
