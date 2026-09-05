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

    def test_growth_sprint_proposal_contract_matches_validator(self) -> None:
        instruction = workflow_instruction(
            "discovery_evidence_to_growth_sprint_proposal",
            "prepare_growth_sprint_proposal",
            ("workstreams_and_questions", "draft_client_communication", "evidence_lineage"),
        )

        self.assertIn("exact key questions", instruction)
        self.assertIn("list of 1–6 distinct, substantive questions", instruction)
        self.assertIn("classification value must be exactly fact, interpretation or hypothesis", instruction)
        self.assertIn("single plain JSON string of 60–500 words, not an object", instruction)

    def test_growth_blueprint_contract_matches_validator(self) -> None:
        instruction = workflow_instruction(
            "research_to_growth_blueprint",
            "prepare_growth_blueprint",
            (
                "fact_interpretation_hypothesis_lineage",
                "evidence_lineage",
                "evidence_and_uncertainty",
                "recommendation",
            ),
        )

        self.assertIn("list of at least three claim-level objects", instruction)
        self.assertIn("exact keys claim, classification and source_refs", instruction)
        self.assertIn("evidence_lineage must be a list of at least five objects", instruction)
        self.assertIn("evidence_and_uncertainty must be a list of at least three", instruction)
        self.assertIn('recommendation must be the exact JSON string "advance"', instruction)


if __name__ == "__main__":
    unittest.main()
