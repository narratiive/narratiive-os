import unittest
from pathlib import Path

from runtime.agent_manifest import load_agent_manifest
from runtime.definitions import load_workflow_definition


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / "workflows" / "growth_blueprint_pipeline.json"

EXPECTED_SPECIALISTS = {
    "research_analyst": "completed_research_inputs",
    "strategy_director": "completed_growth_blueprint",
    "campaign_world_generator": "completed_campaign_world",
    "creative_director": "completed_creative_directors_bible",
    "quality_reviewer": "completed_quality_review",
}


class SpecialistAgentContractTests(unittest.TestCase):
    def test_every_growth_blueprint_stage_has_a_valid_specialist_manifest(self) -> None:
        workflow = load_workflow_definition(WORKFLOW_PATH)
        self.assertEqual(
            [stage.stage_id for stage in workflow.stages],
            list(EXPECTED_SPECIALISTS),
        )

        for stage in workflow.stages:
            manifest_path = REPOSITORY_ROOT / stage.agent_ref
            self.assertTrue(manifest_path.is_file(), f"missing agent manifest: {stage.agent_ref}")
            manifest = load_agent_manifest(manifest_path)
            self.assertEqual(manifest.agent_id, stage.stage_id)
            self.assertTrue(manifest.version)
            for section in ("Purpose", "Inputs", "Outputs", "Rules", "Workflow"):
                self.assertTrue(manifest.section(section), f"empty {section}: {stage.agent_ref}")

    def test_specialists_publish_the_expected_handoff_types(self) -> None:
        workflow = load_workflow_definition(WORKFLOW_PATH)
        for stage in workflow.stages:
            manifest = load_agent_manifest(REPOSITORY_ROOT / stage.agent_ref)
            expected = EXPECTED_SPECIALISTS[stage.stage_id]
            declared = (
                manifest.metadata.get("AI_OUTPUT_TYPE")
                or _output_type_from_operating_contract(manifest.instructions)
            )
            self.assertEqual(declared, expected, f"unexpected output contract: {stage.stage_id}")

    def test_pipeline_handoffs_match_downstream_required_inputs(self) -> None:
        workflow = load_workflow_definition(WORKFLOW_PATH)
        for current, downstream in zip(workflow.stages, workflow.stages[1:]):
            current_manifest = load_agent_manifest(REPOSITORY_ROOT / current.agent_ref)
            output_type = (
                current_manifest.metadata.get("AI_OUTPUT_TYPE")
                or _output_type_from_operating_contract(current_manifest.instructions)
            )
            self.assertIn(output_type, downstream.required_inputs)


def _output_type_from_operating_contract(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("output_type:"):
            return stripped.split(":", 1)[1].strip()
        if stripped.startswith("output_template:"):
            template = stripped.split(":", 1)[1].strip()
            return {
                "templates/Growth_Blueprint.md": "completed_growth_blueprint",
                "templates/Campaign_World.md": "completed_campaign_world",
                "templates/Creative_Directors_Bible.md": "completed_creative_directors_bible",
            }.get(template)
    return None


if __name__ == "__main__":
    unittest.main()
