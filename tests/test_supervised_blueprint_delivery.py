from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.deliverable_production import (
    DeliverableProductionService,
    FakePresentationRenderer,
    FileDeliverableStore,
    presentation_quality_checks,
)
from runtime.supervised_blueprint_delivery import (
    BLUEPRINT_CHAPTERS,
    EVIDENCE_CLASSIFICATIONS,
    SupervisedBlueprintError,
    blueprint_markdown,
    build_supervised_blueprint_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "fieldwork_supervised_blueprint_v2.json"
LEGACY_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "fieldwork_supervised_blueprint.json"


class SupervisedBlueprintDeliveryTests(unittest.TestCase):
    def _intake(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _package(self, root: Path):
        intake = self._intake()
        return build_supervised_blueprint_package(
            intake,
            artifact_catalog=FileArtifactCatalog(
                root / "artifacts",
                workspace_id=intake["identity"]["workspace_id"],
            ),
        )

    def test_vertical_slice_builds_seven_chapters_opening_and_pending_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
        self.assertEqual(
            tuple(chapter["title"] for chapter in package.blueprint["chapters"]),
            BLUEPRINT_CHAPTERS,
        )
        self.assertEqual(len(package.presentation.slides), 20)
        self.assertEqual(len(package.presentation.slides[:5]), 5)
        self.assertEqual(package.presentation.slides[4].layout_type, "creative_proof")
        self.assertEqual(package.presentation.slides[-1].title, "The founder decision")
        self.assertEqual(package.qa_report["status"], "PASS_FOR_HUMAN_REVIEW")
        self.assertEqual(package.approval_checkpoint["status"], "pending")
        self.assertFalse(package.approval_checkpoint["release_authorised"])
        self.assertFalse(package.blueprint["external_action_taken"])
        self.assertTrue(all(presentation_quality_checks(package.presentation).values()))

    def test_commercial_model_reconciles_and_never_calls_scenarios_forecasts(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
        model = package.commercial_model
        self.assertEqual(model["baseline"]["annual_revenue"], 1_200_000)
        self.assertEqual(model["scenarios"][1]["annual_revenue"], 1_890_000)
        self.assertEqual(model["scenarios"][1]["incremental_annual_revenue"], 690_000)
        self.assertEqual(
            sum(item["incremental_annual_revenue"] for item in model["base_scenario_bridge"]),
            690_000,
        )
        self.assertEqual(model["investment_case"]["implementation_investment"], 85_000)
        self.assertEqual(model["scenarios"][0]["year_one_net_after_investment"], -68_260)
        self.assertEqual(model["scenarios"][1]["year_one_incremental_contribution"], 121_440)
        self.assertEqual(model["scenarios"][1]["year_one_net_after_investment"], 36_440)
        self.assertEqual(model["scenarios"][1]["illustrative_payback_months"], 8.4)
        self.assertTrue(all(item["scenario_not_forecast"] for item in model["scenarios"]))

    def test_legacy_issue_471_fixture_remains_supported(self):
        intake = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            package = build_supervised_blueprint_package(
                intake,
                artifact_catalog=FileArtifactCatalog(
                    Path(temporary), workspace_id=intake["identity"]["workspace_id"]
                ),
            )
        self.assertEqual(package.commercial_model["investment_case"]["status"], "incomplete")
        self.assertEqual(package.qa_report["status"], "PASS_FOR_HUMAN_REVIEW")

    def test_evidence_classes_are_strict_and_fictional_verified_claims_fail_closed(self):
        intake = self._intake()
        intake["evidence_ledger"][0]["classification"] = "ESTIMATE"
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            SupervisedBlueprintError, "unsupported evidence classification"
        ):
            build_supervised_blueprint_package(
                intake,
                artifact_catalog=FileArtifactCatalog(Path(temporary), workspace_id="demo-fieldwork"),
            )

        intake = self._intake()
        intake["evidence_ledger"][0]["classification"] = "VERIFIED CLIENT"
        intake["evidence_ledger"][0]["source_document_id"] = "fictional-source"
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            SupervisedBlueprintError, "fictional fixtures cannot claim verified evidence"
        ):
            build_supervised_blueprint_package(
                intake,
                artifact_catalog=FileArtifactCatalog(Path(temporary), workspace_id="demo-fieldwork"),
            )

    def test_lineage_uses_existing_immutable_artifact_catalog_and_specialist_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
        self.assertEqual(
            [record.stage_id for record in package.lineage],
            [
                "research_analyst",
                "research_analyst",
                "strategy_director",
                "strategy_director",
                "campaign_world_generator",
                "creative_director",
                "quality_reviewer",
            ],
        )
        self.assertEqual(package.lineage[-1].parent_artifact_ids, (package.lineage[-2].artifact.artifact_id,))
        self.assertTrue(all(record.workspace_id == "demo-fieldwork" for record in package.lineage))

    def test_existing_deliverable_service_produces_an_internal_review_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._package(root)
            record = DeliverableProductionService(
                FakePresentationRenderer(), FileDeliverableStore(root / "deliverables")
            ).produce(
                package.blueprint,
                specification=package.presentation,
                deliverable_id="fieldwork-demo-v1",
                output_dir=root / "rendered",
                created_at="2026-10-14T00:00:00Z",
            )
        self.assertEqual(record.status, "awaiting_review")
        self.assertEqual(record.approval_status, "pending")
        self.assertFalse(record.external_action_taken)
        self.assertTrue(record.visual_qa.passed)

    def test_markdown_is_explicitly_fictional_and_contains_all_evidence_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
        rendered = blueprint_markdown(package)
        self.assertIn("FICTIONAL DEMONSTRATION", rendered)
        self.assertIn("not forecasts", rendered)
        for chapter in BLUEPRINT_CHAPTERS:
            self.assertIn(f"## {chapter}", rendered)
        for classification in ("MODELLED", "ASSUMPTION", "CREATIVE ILLUSTRATION"):
            self.assertIn(classification, rendered)
        self.assertEqual(
            tuple(package.evidence_ledger["allowed_classifications"]),
            EVIDENCE_CLASSIFICATIONS,
        )


if __name__ == "__main__":
    unittest.main()
