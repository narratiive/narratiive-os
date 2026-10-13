from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.deliverable_production import (
    CANONICAL_BLUEPRINT_SLIDE_TITLES,
    DeliverableProductionService,
    FakePresentationRenderer,
    FileDeliverableStore,
    build_blueprint_director_presentation_spec,
    build_growth_blueprint_presentation_spec,
    build_directed_growth_blueprint_presentation_spec,
    build_quantified_commercial_model,
    augment_specification_with_commercial_evidence,
    commercial_model_quality_checks,
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


def commercial_intelligence() -> dict:
    supporting = [
        {
            "title": f"Synthetic supporting decision {index}",
            "body": "A synthetic, client-neutral execution statement for contract testing.",
            "takeaway": "The execution implication remains bounded and testable.",
            "layout_type": layout,
            "citation_labels": ["T1"],
        }
        for index, layout in enumerate((
            "evidence_ladder", "commercial_sensitivity", "investment_unlock",
            "creative_principles", "channel_applications", "test_plan", "founder_decisions",
        ), 1)
    ]
    return {
        "model_id": "test-commercial-model",
        "currency": "GBP",
        "period": "annual run-rate",
        "inputs": [
            {"input_id": "market_size", "label": "Addressable market estimate", "value": 600000000, "unit": "GBP", "status": "estimate", "source_ids": ["S1"]},
            {"input_id": "current_market_share_percent", "label": "Reported current market share", "value": 2.0, "unit": "percent", "status": "reported_claim", "source_ids": ["S1"]},
        ],
        "scenario_assumptions": [
            {"name": "Conservative", "target_market_share_percent": 2.25, "contribution_margin_percent": 30},
            {"name": "Base", "target_market_share_percent": 2.5, "contribution_margin_percent": 40},
            {"name": "Ambitious", "target_market_share_percent": 3.0, "contribution_margin_percent": 50},
        ],
        "implementation_cost": {"status": "unavailable", "value": None, "missing_inputs": ["delivery budget"]},
        "production_direction": {
            "brand_name": "Northstar Test Co",
            "layout_content": {
                "market_gap_map": {"x_axis": ["Familiar", "Distinctive"], "y_axis": ["Functional", "Authority"], "competitors": [["Category", 25, 25]], "current_position": ["Today", 45, 45], "future_position": ["Opportunity", 80, 80], "market_gap": "A bounded synthetic market gap"},
                "customer_evidence_board": {"signals": [["CUSTOMER SAYS", "Synthetic signal."], ["SEARCH SHOWS", "Synthetic signal."], ["REVIEWS REVEAL", "Synthetic signal."], ["SOCIAL SHOWS", "Synthetic signal."]], "interpretation": "Synthetic interpretation."},
                "positioning_map": {"x_axis": ["Familiar", "Distinctive"], "y_axis": ["Transactional", "Authority"], "positions": [["Today", 40, 40], ["Future", 80, 80]], "territory": "Synthetic territory"},
                "messaging_territories": {"territories": [["Territory one", "Role", "Tension", "Proof", "Asset"], ["Territory two", "Role", "Tension", "Proof", "Asset"], ["Territory three", "Role", "Tension", "Proof", "Asset"]]},
                "attention_strategy": {"items": [["NOTICE", "Signal"], ["REMEMBER", "Message"], ["CONNECT", "Context"], ["VERIFY", "Source"]]},
            },
            "creative_direction": {
                "title": "Creative direction: make the advantage visible",
                "body": "Translate the approved strategy into a recognisable visual system.",
                "takeaway": "A distinctive territory makes the strategic advantage easier to recognise.",
                "primary_phrase": "VISIBLE ADVANTAGE",
                "secondary_phrase": "meets human relevance",
                "principles": ["Observe", "Evidence", "Signal"],
            },
            "supporting_slides": supporting,
        },
    }


def source_register() -> dict:
    refs = [f"ev-{key}" for key in (
        "market_category_diagnosis", "audience", "growth_barriers", "source_of_difference",
        "positioning", "narrative", "growth_opportunity", "activation_implications",
        "key_strategic_choices", "evidence_and_uncertainty",
    )] + [f"ev-{index}" for index in range(1, 18)]
    return {"entries": [
        {"source_id": "S1", "title": "Synthetic source", "publisher": "Test Publisher", "date": "2026", "location": "https://example.test/source", "classification": "verified_fact", "evidence_refs": refs, "applies_to_pages": list(range(2, 31))},
        {"source_id": "S2", "title": "Synthetic science", "publisher": "Test Journal", "date": "2026", "location": "https://example.test/science", "classification": "verified_fact", "evidence_refs": refs, "applies_to_pages": []},
        {"source_id": "T1", "title": "Approved strategy thesis", "publisher": "Narratiive", "date": "2026", "location": "governed runtime artefact", "classification": "approved_strategy", "evidence_refs": ["thesis:thesis_statement"], "applies_to_pages": [1]},
    ]}


class DeliverableProductionTests(unittest.TestCase):
    def test_commercial_model_calculates_scenarios_without_inventing_cost(self) -> None:
        model = build_quantified_commercial_model(commercial_intelligence())
        self.assertEqual(model["estimated_current_annual_revenue"], 12000000)
        self.assertEqual(model["scenarios"][1]["incremental_annual_revenue"], 3000000)
        self.assertEqual(model["scenarios"][1]["incremental_annual_contribution"], 1200000)
        self.assertEqual(model["implementation_cost"]["status"], "unavailable")
        self.assertTrue(all(commercial_model_quality_checks(model).values()))

    def test_commercial_model_rejects_value_when_cost_is_unavailable(self) -> None:
        intelligence = commercial_intelligence()
        intelligence["implementation_cost"] = {"status": "unavailable", "value": 500000}
        with self.assertRaisesRegex(ValueError, "cannot contain an invented value"):
            build_quantified_commercial_model(intelligence)

    def test_augmented_specification_adds_model_sources_and_creative_direction(self) -> None:
        source = artifact()
        spec = build_growth_blueprint_presentation_spec(
            source, specification_id="director-commercial", source_blueprint_id="blueprint-commercial",
            source_blueprint_version=1, workspace_id="workspace-safe", client_id="client-safe",
            title="Northstar Growth Blueprint", brand_name="Northstar",
        )
        result = augment_specification_with_commercial_evidence(
            spec,
            commercial_model=build_quantified_commercial_model(commercial_intelligence()),
            source_register=source_register(),
            production_direction=commercial_intelligence()["production_direction"],
        )
        layouts = [slide.layout_type for slide in result.slides]
        self.assertIn("commercial_model", layouts)
        self.assertIn("creative_direction", layouts)
        self.assertTrue(result.slides[-1].content_data["source_register_entries"])
        self.assertEqual(len(result.slides), 30)
        self.assertEqual(result.slides[22].title, "Commercial Prize")
        self.assertEqual(result.slides[26].title, "Creative Direction / Next-Phase Hook")
        self.assertEqual(result.slides[27].title, "Growth Priorities / 90-Day Activation Plan")
        self.assertEqual(result.slides[28].title, "Measurement Framework")
        self.assertEqual(tuple(slide.title for slide in result.slides), CANONICAL_BLUEPRINT_SLIDE_TITLES)
        checks = presentation_quality_checks(result)
        self.assertTrue(checks["canonical_schema_v3_slide_roles_are_substantive"])
        self.assertTrue(all(slide.body.endswith((".", "?", "!")) for slide in result.slides))
        self.assertTrue(all(slide.takeaway.endswith((".", "?", "!")) for slide in result.slides))
        self.assertTrue(all(slide.slide_no == 1 or slide.citation_labels for slide in result.slides))
        self.assertNotIn("katkin", json.dumps(result.to_dict()).casefold())
        self.assertNotIn("cat behaviour", json.dumps(result.to_dict()).casefold())

    def test_blueprint_director_story_reaches_rendering_without_governance_copy(self) -> None:
        source = {
            "client_facing_blueprint": {
                "title": "Northstar Growth Blueprint",
                "central_argument": "Northstar should concentrate growth around one urgent buyer situation and make credible proof visible earlier in the decision journey.",
                "pages": [
                    {
                        "page_number": index,
                        "act": f"Act {(index - 1) // 5 + 1}",
                        "headline": f"Northstar makes a decisive choice on page {index}",
                        "body": "The page advances the approved strategic argument in concise client-ready language.",
                        "commercial_consequence": "This improves recognition and the quality of commercial response.",
                        "visual_opportunity": "A comparison diagram showing the strategic shift.",
                        "visual_archetype": "argument diagram" if index % 2 else "evidence contrast",
                    }
                    for index in range(1, 18)
                ],
            },
            "editorial_trace": [
                {"page_number": index, "evidence_refs": [f"ev-{index}"]}
                for index in range(1, 18)
            ],
        }
        spec = build_blueprint_director_presentation_spec(
            source, specification_id="director-safe", source_blueprint_id="blueprint-safe",
            source_blueprint_version=1, workspace_id="workspace-safe", client_id="client-safe",
            title="Northstar Growth Blueprint", brand_name="Northstar",
        )
        self.assertEqual(len(spec.slides), 17)
        self.assertEqual(len({slide.layout_type for slide in spec.slides}), 2)
        self.assertTrue(presentation_quality_checks(spec)["editorial_arc_is_complete"])
        self.assertTrue(presentation_quality_checks(spec)["visual_forms_are_intentional"])
        visible = " ".join(f"{slide.title} {slide.takeaway} {slide.body}" for slide in spec.slides)
        self.assertNotIn("evidence_refs", visible)
        self.assertNotIn("ev-", visible)

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
        self.assertEqual(tuple(slide.title for slide in spec.slides), CANONICAL_BLUEPRINT_SLIDE_TITLES)
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
