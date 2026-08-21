from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TONY_ALLOW = {
    "agents_list",
    "sessions_history",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "narratiive-control-plane",
}
EXPECTED_NARRATIIVE_TOOLS = {
    "narratiive_read_state",
    "narratiive_execute_safe_read",
    "narratiive_request_action_approval",
}


class TonyExplicitToolProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        fleet = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        self.tony = next(agent for agent in fleet["agents"]["list"] if agent["id"] == "tony")
        self.manifest = json.loads(
            (ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "openclaw.plugin.json").read_text(encoding="utf-8")
        )

    def test_tony_owns_explicit_messaging_profile_instead_of_inheriting_global_profile(self) -> None:
        tools = self.tony["tools"]
        self.assertEqual(tools["profile"], "messaging")
        self.assertEqual(set(tools["allow"]), EXPECTED_TONY_ALLOW)
        self.assertNotIn("sessions_list", tools["allow"])
        self.assertNotIn("session_status", tools["allow"])
        self.assertNotIn("read", tools["allow"])
        self.assertNotIn("exec", tools["allow"])

    def test_all_control_plane_tools_are_members_of_messaging_profile(self) -> None:
        metadata = self.manifest["toolMetadata"]
        self.assertEqual(set(metadata), EXPECTED_NARRATIIVE_TOOLS)
        for tool in EXPECTED_NARRATIIVE_TOOLS:
            with self.subTest(tool=tool):
                self.assertIn("messaging", metadata[tool]["profiles"])

    def test_manifest_contract_and_profile_metadata_stay_in_sync(self) -> None:
        contracted = set(self.manifest["contracts"]["tools"])
        profiled = set(self.manifest["toolMetadata"])
        self.assertEqual(contracted, EXPECTED_NARRATIIVE_TOOLS)
        self.assertEqual(profiled, contracted)


if __name__ == "__main__":
    unittest.main()
