from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OpenClawSpecialistRosterTests(unittest.TestCase):
    def setUp(self):
        self.roster = json.loads((ROOT / "openclaw" / "specialists.json").read_text(encoding="utf-8"))

    def test_tony_is_single_orchestrator_with_canonical_specialists(self):
        self.assertEqual(self.roster["orchestrator"], "tony")
        self.assertEqual(
            [item["id"] for item in self.roster["specialists"]],
            ["research", "strategy", "creative-director", "production", "operations"],
        )
        self.assertTrue(all(item["mission"].strip() for item in self.roster["specialists"]))

    def test_specialist_policy_preserves_control_plane_boundary(self):
        policy = self.roster["policy"]
        self.assertEqual(policy["conversation_owner"], "tony")
        self.assertEqual(policy["default_delegation"], "isolated")
        self.assertEqual(policy["consequential_writes"], "approval_required")
        self.assertTrue(policy["completion_requires_evidence"])

    def test_tony_workspace_carries_the_canonical_known_roster(self):
        contract = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        fleet = json.loads((ROOT / "openclaw" / "openclaw.fleet.json").read_text(encoding="utf-8"))
        configured = {agent["id"]: agent for agent in fleet["agents"]["list"]}
        for specialist in self.roster["specialists"]:
            with self.subTest(agent_id=specialist["id"]):
                self.assertIn(specialist["id"], contract)
                self.assertIn(specialist["name"], contract)
                self.assertEqual(configured[specialist["id"]]["name"], specialist["name"])
        self.assertIn("You orchestrate five specialists as the canonical configured team", contract)
        self.assertIn("This roster exists independently of whether any child job is running", contract)

    def test_multi_agent_contract_uses_native_openclaw_orchestration_not_phrase_matching(self):
        contract = (ROOT / "openclaw" / "TONY_MULTI_AGENT.md").read_text(encoding="utf-8")
        for tool in ("agents_list", "sessions_spawn", "sessions_history", "sessions_yield", "subagents"):
            self.assertIn(tool, contract)
        self.assertNotIn("`sessions_list`", contract)
        self.assertIn("without phrase-specific Python routing", contract)
        self.assertIn("approval/evidence boundaries", contract)


if __name__ == "__main__":
    unittest.main()
