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
    build_directed_growth_blueprint_presentation_spec,
    presentation_quality_checks,
    _safe_rendered_path,
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
            workspace_id="safe-northstar",
            client_id="northstar-test-co",
            title="Narratiive Growth Blueprint — Northstar Test Co",
            brand_name="Northstar Test Co",
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
            workspace_id="safe-northstar",
            client_id="northstar-test-co",
            title="Narratiive Growth Blueprint — Northstar Test Co",
            brand_name="Northstar Test Co",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = DeliverableProductionService(
                FakePresentationRenderer(), FileDeliverableStore(root / "records")
            ).produce(
                source,
                specification=spec,
                deliverable_id="northstar-blueprint-deliverable-v1",
                output_dir=root / "outputs",
                created_at="2026-09-07T00:00:00+00:00",
            )
            self.assertEqual(record.status, "awaiting_review")
            self.assertEqual(record.approval_status, "pending")
            self.assertFalse(record.external_action_taken)
            self.assertTrue(Path(record.pptx_path).exists())
            self.assertTrue(Path(record.pdf_path).exists())
            self.assertTrue((root / "records" / "safe-northstar" / "northstar-test-co" / "northstar-blueprint-deliverable-v1.json").exists())

    def test_quality_gate_rejects_missing_visual_qa_or_external_action(self) -> None:
        failed = growth_blueprint_deliverable_quality_gate(
            {"presentation_specification": {}, "editable_pptx": "deck.pptx", "review_pdf": "deck.pdf", "visual_qa": {"status": "passed", "checks": {"fit": True}}, "approval_status": "pending", "external_action_taken": True}
        )
        self.assertFalse(failed["passed"])
        self.assertIn("no external action taken", failed["failed_checks"])

    def test_presentation_director_creates_editorial_arc_without_visible_lineage_ids(self) -> None:
        spec = build_directed_growth_blueprint_presentation_spec(
            artifact(), specification_id="director-1", source_blueprint_id="blueprint-rave",
            source_blueprint_version=1, workspace_id="safe-northstar", client_id="northstar", title="Northstar Test Co",
            brand_name="Northstar Test Co",
        )
        self.assertGreaterEqual(len(spec.slides), 12)
        self.assertGreaterEqual(len({slide.layout_type for slide in spec.slides}), 8)
        visible = " ".join(f"{s.title} {s.takeaway} {s.body}" for s in spec.slides)
        self.assertNotIn("ev-", visible)
        self.assertNotIn("Rave", visible)
        self.assertNotIn("coffee", visible.casefold())
        self.assertIn("Northstar Test Co", visible)
        self.assertTrue(presentation_quality_checks(spec)["no_visible_machine_runtime_artefacts"])
        self.assertTrue(all(slide.evidence_refs for slide in spec.slides))

    def test_renderer_receipt_path_must_remain_inside_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "outputs"
            output.mkdir()
            expected = output / "Northstar-Growth-Blueprint-v1.pptx"
            self.assertEqual(
                _safe_rendered_path(output, str(expected), suffix=".pptx"),
                expected.resolve(),
            )
            with self.assertRaisesRegex(RuntimeError, "unsafe output path"):
                _safe_rendered_path(output, "../escaped.pptx", suffix=".pptx")

    def test_record_store_loads_exact_scope_and_rejects_unsafe_identity(self) -> None:
        source = artifact()
        spec = build_growth_blueprint_presentation_spec(
            source,
            specification_id="spec-northstar-load",
            source_blueprint_id="blueprint-northstar",
            source_blueprint_version=1,
            workspace_id="safe-northstar",
            client_id="northstar-test-co",
            title="Narratiive Growth Blueprint — Northstar Test Co",
            brand_name="Northstar Test Co",
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = FileDeliverableStore(Path(temporary) / "records")
            record = DeliverableProductionService(FakePresentationRenderer(), store).produce(
                source,
                specification=spec,
                deliverable_id="northstar-load-v1",
                output_dir=Path(temporary) / "outputs",
                created_at="2026-09-18T00:00:00Z",
            )
            self.assertEqual(store.load("safe-northstar", "northstar-test-co", "northstar-load-v1"), record)
            with self.assertRaisesRegex(ValueError, "safe identifiers"):
                store.load("../escaped", "northstar-test-co", "northstar-load-v1")

            unsafe = record.__class__(
                **{**record.to_dict(), "workspace_id": "../escaped", "visual_qa": record.visual_qa}
            )
            with self.assertRaisesRegex(ValueError, "safe identifiers"):
                store.save(unsafe)


if __name__ == "__main__":
    unittest.main()
