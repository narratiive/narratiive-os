from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw" / "plugins" / "narratiive-control-plane"


class OpenClawNativeActionApprovalTests(unittest.TestCase):
    def _node_json(self, export_name: str, payload: dict) -> dict:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        module_uri = (PLUGIN / "approval-policy.js").resolve().as_uri()
        script = (
            f'import {{ {export_name} }} from {json.dumps(module_uri)}; '
            f'console.log(JSON.stringify({export_name}({json.dumps(payload)})));'
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_manifest_declares_native_approval_tool(self):
        manifest = json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))
        self.assertIn("narratiive_request_action_approval", manifest["contracts"]["tools"])

    def test_consequential_send_requires_single_use_native_approval(self):
        result = self._node_json(
            "buildNativeApprovalRequirement",
            {
                "action": "send the email to Jimmy using Thursday",
                "surface": "gmail",
                "kind": "write",
                "target": {"contact": "Jimmy"},
            },
        )
        self.assertTrue(result["required"])
        approval = result["requireApproval"]
        self.assertEqual(approval["allowedDecisions"], ["allow-once", "deny"])
        self.assertEqual(approval["severity"], "warning")
        self.assertIn("Jimmy", approval["description"])
        self.assertLessEqual(len(approval["title"]), 80)
        self.assertLessEqual(len(approval["description"]), 512)

    def test_read_only_action_does_not_create_an_approval_prompt(self):
        result = self._node_json(
            "buildNativeApprovalRequirement",
            {"action": "check my calendar availability", "surface": "calendar", "kind": "read"},
        )
        self.assertFalse(result["required"])
        self.assertNotIn("requireApproval", result)

    def test_approved_result_is_not_execution_evidence(self):
        result = self._node_json(
            "approvedActionResult",
            {
                "action": "send the email to Jimmy",
                "surface": "gmail",
                "kind": "write",
                "target": {"contact": "Jimmy"},
            },
        )
        self.assertTrue(result["approval_granted"])
        self.assertEqual(result["approval_scope"]["decision"], "allow-once")
        self.assertTrue(result["approval_scope"]["single_use"])
        self.assertFalse(result["external_action_taken"])
        self.assertEqual(result["execution_truth"], "approved_not_dispatched")
        self.assertIn("verify returned execution evidence", result["next_step"])

    def test_engineering_surfaces_get_critical_approval_severity(self):
        for surface in ("github", "n8n", "replit"):
            with self.subTest(surface=surface):
                result = self._node_json(
                    "buildNativeApprovalRequirement",
                    {"action": "deploy the change", "surface": surface, "kind": "write"},
                )
                self.assertTrue(result["required"])
                self.assertEqual(result["requireApproval"]["severity"], "critical")

    def test_plugin_uses_before_tool_call_native_approval_hook(self):
        source = (PLUGIN / "index.js").read_text(encoding="utf-8")
        self.assertIn('api.on("before_tool_call"', source)
        self.assertIn('event.toolName !== "narratiive_request_action_approval"', source)
        self.assertIn("requireApproval", source)
        self.assertIn("allowedDecisions", (PLUGIN / "approval-policy.js").read_text(encoding="utf-8"))

    def test_tony_uses_native_approval_without_magic_phrase_and_keeps_evidence_boundary(self):
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("narratiive_request_action_approval", prompt)
        self.assertIn("Do not make Matt restate a magic approval phrase", prompt)
        self.assertIn("Approval authorises only that exact proposed action and is not execution", prompt)
        self.assertIn("verify returned evidence", prompt)
        self.assertIn("single-use", prompt)


if __name__ == "__main__":
    unittest.main()
