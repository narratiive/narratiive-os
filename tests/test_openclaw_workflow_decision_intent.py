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
            f'import {{ hasExplicitWorkflowDecisionIntent, buildTrustedWorkflowClassificationParams, buildTrustedWorkflowDecisionParams, buildTrustedWorkflowRecoveryParams }} from {json.dumps(MODULE.resolve().as_uri())}; '
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

    def test_synthetic_classification_binds_current_turn_and_exact_entity(self) -> None:
        prompt = "Classify inbound-d1b96a67 as a synthetic internal test."
        params = {
            "operation": "classify_synthetic_test",
            "reference": "inbound-d1b96a67",
            "rationale": "Founder-authorised internal certification record.",
            "classification_instruction": prompt,
            "authorisation_reference": "telegram-message:513",
        }
        result = self._node(
            f"buildTrustedWorkflowClassificationParams({json.dumps(params)},{{runId:'conversation-turn-1',prompt:{json.dumps(prompt)}}},'secret')"
        )
        self.assertEqual(result["classification_instruction"], prompt)
        self.assertEqual(result["_classification_instruction_run_id"], "conversation-turn-1")
        self.assertEqual(len(result["_classification_instruction_proof"]), 64)

        altered = dict(params, reference="another-entity")
        expression = (
            "(()=>{try{buildTrustedWorkflowClassificationParams("
            f"{json.dumps(altered)},{{runId:'conversation-turn-1',prompt:{json.dumps(prompt)}}},'secret');return 'allowed'"
            "}catch(error){return error.message}})()"
        )
        self.assertIn("exact workflow entity", self._node(expression))

    def test_manual_recovery_binds_the_current_human_instruction(self) -> None:
        prompt = "Recover the existing fictional Origin engagement through the canonical workflow state."
        params = {
            "operation": "manual_recovery",
            "reference": "origin-fictional-run",
            "rationale": "Use the approved immutable recovery artefact.",
            "recovery_instruction": prompt,
            "authorisation_reference": "chat-message:origin-recovery",
            "manual_recovery": {
                "recovery_id": "origin-groundwork-v1",
                "artifact_title": "Origin Coffee Groundwork Review",
                "artifact_version": "v1",
                "source_uri": "https://docs.example.invalid/origin/v1",
                "artifact_checksum": "a" * 64,
                "output": {"blueprint_lite": "approved"},
            },
        }
        result = self._node(
            f"buildTrustedWorkflowRecoveryParams({json.dumps(params)},{{runId:'conversation-turn-2',prompt:{json.dumps(prompt)}}},'secret')"
        )
        self.assertEqual(result["recovery_instruction"], prompt)
        self.assertEqual(result["_recovery_instruction_run_id"], "conversation-turn-2")
        self.assertEqual(len(result["_recovery_instruction_proof"]), 64)

        changed = json.loads(json.dumps(params))
        changed["manual_recovery"]["artifact_checksum"] = "b" * 64
        expression = (
            "(()=>{const turn={runId:'conversation-turn-2',prompt:"
            f"{json.dumps(prompt)}"
            "};buildTrustedWorkflowRecoveryParams("
            f"{json.dumps(params)},turn,'secret');try{{buildTrustedWorkflowRecoveryParams({json.dumps(changed)},turn,'secret');return 'allowed'}}"
            "catch(error){return error.message}})()"
        )
        self.assertIn("different manual recovery", self._node(expression))

        refused = dict(params, recovery_instruction="Do not recover the existing fictional Origin engagement workflow.")
        expression = (
            "(()=>{try{buildTrustedWorkflowRecoveryParams("
            f"{json.dumps(refused)},{{runId:'conversation-turn-2',prompt:{json.dumps(refused['recovery_instruction'])}}},'secret');return 'allowed'"
            "}catch(error){return error.message}})()"
        )
        self.assertIn("refuses", self._node(expression))

        question = dict(params, recovery_instruction="Is the workflow recovery still blocked?")
        expression = (
            "(()=>{try{buildTrustedWorkflowRecoveryParams("
            f"{json.dumps(question)},{{runId:'conversation-turn-3',prompt:{json.dumps(question['recovery_instruction'])}}},'secret');return 'allowed'"
            "}catch(error){return error.message}})()"
        )
        self.assertIn("not recovery authorisation", self._node(expression))

        non_authorising = [
            "Please tell me whether the workflow recovery is still blocked.",
            "Give me the workflow recovery state.",
            "The workflow recovery state is blocked.",
            "I do not want you to recover the workflow.",
            "Don't attempt to recover the workflow.",
            "I request the workflow recovery state.",
            "I request an update on workflow recovery.",
            "I approve this summary of the workflow recovery state.",
        ]
        for index, statement in enumerate(non_authorising, start=4):
            candidate = dict(params, recovery_instruction=statement)
            expression = (
                "(()=>{try{buildTrustedWorkflowRecoveryParams("
                f"{json.dumps(candidate)},{{runId:'conversation-turn-{index}',prompt:{json.dumps(statement)}}},'secret');return 'allowed'"
                "}catch(error){return error.message}})()"
            )
            self.assertNotEqual(self._node(expression), "allowed", statement)


if __name__ == "__main__":
    unittest.main()
