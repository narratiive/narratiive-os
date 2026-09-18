from __future__ import annotations

import unittest

from runtime.workflow_instructions import workflow_instruction


class WorkflowInstructionTests(unittest.TestCase):
    def test_blueprint_lite_contract_matches_validator(self) -> None:
        instruction = workflow_instruction(
            "growth_diagnostic_to_blueprint_lite",
            "prepare_blueprint_lite",
            ("diagnostic_input_coverage", "questions_to_answer_next"),
        )

        self.assertIn("exact boolean key complete", instruction)
        self.assertIn("Do not use status as a substitute for complete", instruction)
        self.assertIn("exactly 3 or 4 distinct, substantive questions", instruction)
        self.assertIn("exact singular keys fact, interpretation and hypothesis", instruction)
        self.assertIn("human_review_ready=true", instruction)

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

    def test_campaign_world_contract_matches_validator(self) -> None:
        instruction = workflow_instruction(
            "growth_blueprint_to_campaign_world",
            "generate_campaign_world",
            ("campaign_world", "strategic_handoff", "evidence_lineage"),
        )

        self.assertIn("Campaign World Schema v1", instruction)
        self.assertIn("at least three complete campaign territories", instruction)
        self.assertIn("all eight canonical channel translations", instruction)
        self.assertIn("Matt selection", instruction)

    def test_creative_bible_contract_matches_validator(self) -> None:
        instruction = workflow_instruction(
            "campaign_world_to_creative_bible",
            "prepare_creative_bible",
            ("creative_directors_bible",),
        )

        self.assertIn("Creative Director's Bible v2", instruction)
        self.assertIn("twenty complete image prompts", instruction)
        self.assertIn("ten complete video prompts", instruction)
        self.assertIn("Matt approval", instruction)


if __name__ == "__main__":
    unittest.main()
