from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw" / "plugins" / "narratiive-control-plane"


class OpenClawActionPolicyTests(unittest.TestCase):
    def test_manifest_exposes_execution_boundaries_without_model_proposal_tool(self):
        manifest = json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))
        tools = set(manifest["contracts"]["tools"])
        self.assertNotIn("narratiive_propose_action", tools)
        self.assertIn("narratiive_execute_safe_read", tools)
        self.assertIn("narratiive_request_action_approval", tools)

        source = (PLUGIN / "index.js").read_text(encoding="utf-8")
        self.assertNotIn('name: "narratiive_propose_action"', source)
        self.assertNotIn("api.registerTool(proposalTool())", source)

    def test_tony_workspace_selects_typed_consequence_boundary_directly(self):
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("narratiive_propose_action", prompt)
        self.assertIn("narratiive_execute_safe_read", prompt)
        self.assertIn("narratiive_request_action_approval", prompt)
        self.assertIn("native single-use approval gate", prompt)
        self.assertIn("verify returned evidence", prompt)
        self.assertIn("sort that out", prompt)
        self.assertIn("send it", prompt)
        self.assertIn("contextual turns, not commands to phrase-match", prompt)

    def _proposal(self, payload: dict) -> dict:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        module_uri = (PLUGIN / "action-policy.js").resolve().as_uri()
        script = (
            f'import {{ buildActionProposal }} from {json.dumps(module_uri)}; '
            f'console.log(JSON.stringify(buildActionProposal({json.dumps(payload)})));'
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_internal_policy_still_allows_verified_read_only_calendar_check(self):
        result = self._proposal({"action": "check my calendar availability on Thursday", "surface": "calendar", "kind": "read"})
        proposal = result["proposal"]
        self.assertFalse(proposal["approval_required"])
        self.assertEqual(proposal["execution_mode"], "autonomous_read")
        self.assertEqual(proposal["dispatch"]["state"], "ready_for_autonomous_dispatch")
        self.assertFalse(result["external_action_taken"])
        self.assertEqual(result["execution_truth"], "proposal_only_not_dispatched")

    def test_internal_policy_allows_reversible_preparation_without_permission(self):
        result = self._proposal({"action": "prepare a reply for Jimmy without sending it", "surface": "gmail", "kind": "prepare"})
        proposal = result["proposal"]
        self.assertFalse(proposal["approval_required"])
        self.assertEqual(proposal["execution_mode"], "autonomous_prepare")
        self.assertFalse(result["approval_granted"])

    def test_send_language_cannot_be_downgraded_by_model_to_read_or_prepare(self):
        for kind in ("read", "prepare", "write"):
            with self.subTest(kind=kind):
                result = self._proposal({"action": "send the email to Jimmy", "surface": "gmail", "kind": kind})
                proposal = result["proposal"]
                self.assertEqual(proposal["effective_kind"], "write")
                self.assertTrue(proposal["approval_required"])
                self.assertEqual(proposal["execution_mode"], "approval_gated_write")
                self.assertEqual(proposal["dispatch"]["state"], "awaiting_approval")
                self.assertFalse(proposal["dispatch"]["eligible"])
                self.assertFalse(result["external_action_taken"])

    def test_ambiguous_other_surface_fails_conservatively_for_reads(self):
        result = self._proposal({"action": "check that system", "surface": "other", "kind": "read"})
        proposal = result["proposal"]
        self.assertTrue(proposal["approval_required"])
        self.assertEqual(proposal["execution_mode"], "approval_gated_write")


if __name__ == "__main__":
    unittest.main()
