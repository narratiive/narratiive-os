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


if __name__ == "__main__":
    unittest.main()
