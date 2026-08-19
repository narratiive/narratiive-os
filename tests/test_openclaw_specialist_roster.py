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

    def test_multi_agent_contract_uses_native_openclaw_orchestration_not_phrase_matching(self):
        contract = (ROOT / "openclaw" / "TONY_MULTI_AGENT.md").read_text(encoding="utf-8")
        for tool in ("agents_list", "sessions_spawn", "sessions_list", "sessions_history", "sessions_yield", "subagents"):
            self.assertIn(tool, contract)
        self.assertIn("without phrase-specific Python routing", contract)
        self.assertIn("approval/evidence boundaries", contract)


if __name__ == "__main__":
    unittest.main()
