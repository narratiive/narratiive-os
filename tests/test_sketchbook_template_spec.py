import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "outputs" / "prototypes" / "rave-sketchbook"


class SketchbookTemplateSpecificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads((PROTOTYPE / "template-specification.json").read_text())

    def test_contains_the_five_canonical_page_types_in_order(self) -> None:
        self.assertEqual(
            [page["id"] for page in self.spec["page_types"]],
            [
                "creative_proposition",
                "audience_profile",
                "visual_world",
                "campaign_territory",
                "campaign_executions",
            ],
        )

    def test_every_page_has_population_and_failure_contracts(self) -> None:
        for page in self.spec["page_types"]:
            with self.subTest(page=page["id"]):
                self.assertTrue(page["required_fields"])
                self.assertTrue(page["geometry_px"])
                self.assertTrue(page["text_constraints"])
                self.assertTrue(page["approved_variants"])
                self.assertTrue(page["overflow"])
                self.assertTrue(page["missing_content"])

    def test_spec_preserves_human_and_evidence_gates(self) -> None:
        self.assertEqual(
            self.spec["human_approval"],
            "required_before_client_or_production_use",
        )
        checks = " ".join(self.spec["visual_qa_checks"]).lower()
        self.assertIn("unverified", checks)
        self.assertIn("internal/not-client-approved", checks)
        self.assertIn("editable text", checks)

    def test_review_artefacts_and_lineage_exist(self) -> None:
        expected = [
            "INTERNAL-Rave-SKETCHBOOK-canonical-prototype-v2.pptx",
            "INTERNAL-Rave-SKETCHBOOK-canonical-prototype-v2.pdf",
            "source-provenance.json",
            "visual-qa-report.md",
        ]
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue((PROTOTYPE / name).is_file())


if __name__ == "__main__":
    unittest.main()
