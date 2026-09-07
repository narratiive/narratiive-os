from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.deliverable_production import (
    DeliverableProductionService,
    FakePresentationRenderer,
    FileDeliverableStore,
    build_growth_blueprint_presentation_spec,
)
from runtime.workflow_quality import growth_blueprint_deliverable_quality_gate


def artifact() -> dict:
    def section(text: str, refs: list[str]) -> dict:
        return {
            "diagnosis": text,
            "implication": text + " The implication is bounded and requires human review.",
            "uncertainties": ["The source artefact does not contain company-internal validation."],
            "evidence_refs": refs,
        }

    return {
        key: section(f"Evidence-backed {key} conclusion with explicit uncertainty.", [f"ev-{key}"])
        for key in (
            "market_category_diagnosis", "audience", "growth_barriers", "source_of_difference",
            "positioning", "narrative", "growth_opportunity", "activation_implications",
            "key_strategic_choices", "evidence_and_uncertainty",
        )
    }


class DeliverableProductionTests(unittest.TestCase):
    def test_specification_preserves_source_and_canonical_slide_order(self) -> None:
        source = artifact()
        spec = build_growth_blueprint_presentation_spec(
            source,
            specification_id="spec-rave-1",
            source_blueprint_id="blueprint-rave",
            source_blueprint_version=1,
            workspace_id="safe-rave",
            client_id="rave-coffee-safe-no-contact",
            title="Narratiive Growth Blueprint — Rave Coffee",
        )
        self.assertEqual(len(spec.slides), 30)
        self.assertEqual(spec.slides[0].layout_type, "cover")
        self.assertEqual(spec.slides[-1].slide_no, 30)
        self.assertTrue(spec.strategic_source_unchanged)
        self.assertIn("native PPTX template not present", spec.template_source)

    def test_production_is_idempotently_recorded_as_human_review_pending(self) -> None:
        source = artifact()
        spec = build_growth_blueprint_presentation_spec(
            source,
            specification_id="spec-rave-1",
            source_blueprint_id="blueprint-rave",
            source_blueprint_version=1,
            workspace_id="safe-rave",
            client_id="rave-coffee-safe-no-contact",
            title="Narratiive Growth Blueprint — Rave Coffee",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = DeliverableProductionService(
                FakePresentationRenderer(), FileDeliverableStore(root / "records")
            ).produce(
                source,
                specification=spec,
                deliverable_id="rave-blueprint-deliverable-v1",
                output_dir=root / "outputs",
                created_at="2026-09-07T00:00:00+00:00",
            )
            self.assertEqual(record.status, "awaiting_review")
            self.assertEqual(record.approval_status, "pending")
            self.assertFalse(record.external_action_taken)
            self.assertTrue(Path(record.pptx_path).exists())
            self.assertTrue(Path(record.pdf_path).exists())
            self.assertTrue((root / "records" / "safe-rave" / "rave-coffee-safe-no-contact" / "rave-blueprint-deliverable-v1.json").exists())

    def test_quality_gate_rejects_missing_visual_qa_or_external_action(self) -> None:
        failed = growth_blueprint_deliverable_quality_gate(
            {"presentation_specification": {}, "editable_pptx": "deck.pptx", "review_pdf": "deck.pdf", "visual_qa": {"status": "passed", "checks": {"fit": True}}, "approval_status": "pending", "external_action_taken": True}
        )
        self.assertFalse(failed["passed"])
        self.assertIn("no external action taken", failed["failed_checks"])


if __name__ == "__main__":
    unittest.main()
