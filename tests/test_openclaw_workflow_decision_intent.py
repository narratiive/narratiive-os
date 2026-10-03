from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "openclaw" / "plugins" / "narratiive-control-plane" / "workflow-decision-intent.js"


class OpenClawWorkflowDecisionIntentTests(unittest.TestCase):
    def _node(self, expression: str):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        script = (
            f'import {{ hasExplicitWorkflowDecisionIntent, buildTrustedWorkflowDecisionParams }} from {json.dumps(MODULE.resolve().as_uri())}; '
            f"console.log(JSON.stringify({expression}));"
        )
        completed = subprocess.run([node, "--input-type=module", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(completed.stdout)

    def test_general_progress_language_is_never_artefact_approval(self) -> None:
        for instruction in ("We've won it. Get us ready to start", "proceed", "looks good", "continue"):
            with self.subTest(instruction=instruction):
                self.assertFalse(self._node(f"hasExplicitWorkflowDecisionIntent('approve', {json.dumps(instruction)})"))

    def test_explicit_artefact_decisions_are_operation_specific(self) -> None:
        cases = (
            ("approve", "I explicitly approve the current Blueprint Lite artefact."),
            ("reject", "I reject the current Strategy Thesis artefact."),
            ("request_revision", "Please revise the current Growth Blueprint artefact."),
        )
        for operation, instruction in cases:
            with self.subTest(operation=operation):
                self.assertTrue(self._node(f"hasExplicitWorkflowDecisionIntent({json.dumps(operation)}, {json.dumps(instruction)})"))
        self.assertFalse(self._node("hasExplicitWorkflowDecisionIntent('approve', 'Do not approve the current Blueprint Lite artefact.')"))
        self.assertFalse(self._node("hasExplicitWorkflowDecisionIntent('approve', 'Can I approve the current Blueprint Lite artefact?')"))

    def test_model_cannot_paraphrase_or_manufacture_the_human_instruction(self) -> None:
        prompt = "I approve the current Blueprint Lite artefact."
        params = {
            "operation": "approve",
            "reference": "safe-run",
            "approval_token": "a" * 64,
            "approval_instruction": "The human approved the current Blueprint Lite artefact.",
        }
        expression = (
            "(()=>{try{buildTrustedWorkflowDecisionParams("
            f"{json.dumps(params)},{{runId:'run-1',prompt:{json.dumps(prompt)}}},'secret');return 'allowed'"
            "}catch(error){return error.message}})()"
        )
        self.assertIn("exactly equal", self._node(expression))

    def test_verified_params_bind_current_turn_operation_reference_and_token(self) -> None:
        prompt = "I approve the current Blueprint Lite artefact."
        params = {"operation": "approve", "reference": "safe-run", "approval_token": "a" * 64, "approval_instruction": prompt}
        result = self._node(
            f"buildTrustedWorkflowDecisionParams({json.dumps(params)},{{runId:'turn-1',prompt:{json.dumps(prompt)}}},'secret')"
        )
        self.assertEqual(result["approval_instruction"], prompt)
        self.assertEqual(result["_approval_instruction_run_id"], "turn-1")
        self.assertEqual(len(result["_approval_instruction_proof"]), 64)


if __name__ == "__main__":
    unittest.main()
