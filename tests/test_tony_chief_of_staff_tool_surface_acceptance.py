from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_tony_openclaw_live import SCENARIOS, run_live_probe


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TONY_TOOLS = {
    "agents_list",
    "sessions_history",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
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
            prompt = str((body or {}).get("input") or "")
            if "across Narratiive" in prompt:
                text = "Research, Strategy, Creative, Production and Operations are configured and available; no child job is currently running. Mission Control shows the current commercial priority."
            elif "Ask the Research Agent" in prompt:
                text = "Research assignment started and is working in a visible specialist session."
            elif "Research Agent" in prompt:
                text = "Research is working in its delegated specialist session."
            else:
                text = f"natural Chief of Staff reply {index}"
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
        self.assertEqual(agents["tony"]["tools"]["profile"], "messaging")
        allowed = set(agents["tony"]["tools"]["allow"])
        self.assertEqual(allowed, EXPECTED_TONY_TOOLS)
        self.assertNotIn("sessions_list", allowed)
        self.assertNotIn("session_status", allowed)
        self.assertNotIn("read", allowed)
        self.assertIn("read", agents["research"]["tools"]["allow"])
        self.assertIn("write", agents["research"]["tools"]["allow"])
        self.assertIn("read", agents["operations"]["tools"]["allow"])

    def test_specialist_status_uses_subagent_registry_then_bounded_history(self) -> None:
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("`agents_list` is the authoritative discovery view", prompt)
        self.assertIn("`subagents` is a separate live/recent run ledger", prompt)
        self.assertIn("call `agents_list` for configured availability and `subagents`", prompt)
        self.assertIn("Do not broaden the search with `sessions_list`", prompt)
        self.assertIn("use `session_status` for specialist tracking", prompt)
        self.assertIn("bounded transcript with `sessions_history`", prompt)
        self.assertIn("no child job currently running", prompt)
        self.assertIn("never turn `no child job currently running` into `no specialists` or `no active projects`", prompt)

    def test_material_specialist_work_uses_openclaw_persistent_sessions(self) -> None:
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("spawn it with `visible: true`", prompt)
        self.assertIn('`category: "Narratiive specialists"`', prompt)
        self.assertIn("native persistent specialist-session mode", prompt)
        self.assertIn("default hidden sub-agent mode only for short internal work", prompt)
        self.assertIn("sessionUrl", prompt)
        self.assertIn("Do not create a second Narratiive-side specialist registry", prompt)

        fleet = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        agents = {agent["id"]: agent for agent in fleet["agents"]["list"]}
        self.assertEqual(agents["tony"]["subagents"]["delegationMode"], "prefer")
        self.assertEqual(
            set(agents["tony"]["subagents"]["allowAgents"]),
            {"research", "strategy", "creative-director", "production", "operations"},
        )

    def test_control_plane_contract_is_three_stable_capability_tools(self) -> None:
        manifest = json.loads(
            (ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "openclaw.plugin.json").read_text(encoding="utf-8")
        )
        tools = set(manifest["contracts"]["tools"])
        self.assertEqual(tools, EXPECTED_CONTROL_PLANE_TOOLS)
        self.assertEqual(set(manifest["toolMetadata"]), EXPECTED_CONTROL_PLANE_TOOLS)
        for tool in EXPECTED_CONTROL_PLANE_TOOLS:
            self.assertIn("messaging", manifest["toolMetadata"][tool]["profiles"])
        self.assertTrue(LEGACY_STATE_TOOLS.isdisjoint(tools))
        self.assertNotIn("narratiive_propose_action", tools)

        source = (ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "index.js").read_text(encoding="utf-8")
        self.assertIn('name: "narratiive_read_state"', source)
        self.assertIn('["executive_brief", "current_leads", "open_work", "recent_execution"]', source)
        self.assertIn('if (view === "open_work") return "/mission";', source)
        self.assertNotIn('return "/what\'s the status"', source)
        self.assertIn("TONY_CONTROL_PLANE_TIMEOUT_MS", source)
        self.assertIn("AbortSignal.timeout(timeoutMs)", source)
        self.assertIn("Narratiive control plane timed out after", source)
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
        self.assertIn("call the tool and finish the same conversational turn with the result", prompt)
        self.assertIn("Do not leave Matt with a standalone progress preamble", prompt)
        self.assertIn("A progress acknowledgement is not a completed answer", prompt)
        self.assertIn("read `executive_brief`, `open_work` and `current_leads`", prompt)
        self.assertIn("before asking Matt for outreach targets, goals, contacts, leads", prompt)

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
