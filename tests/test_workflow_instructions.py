from __future__ import annotations

import unittest

from runtime.workflow_instructions import workflow_instruction


class WorkflowInstructionTests(unittest.TestCase):
    def test_discovery_hypothesis_contract_matches_validator(self) -> None:
        instruction = workflow_instruction(
            "blueprint_lite_to_discovery_preparation",
            "prepare_discovery",
            ("discovery_hypotheses",),
        )

        self.assertIn("at least three objects", instruction)
        self.assertIn("evidence-grounded basis", instruction)
        self.assertIn("one or more evidence_refs", instruction)
        self.assertIn("validation_question ending with a question mark (?)", instruction)


if __name__ == "__main__":
    unittest.main()
