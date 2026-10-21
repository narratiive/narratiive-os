from __future__ import annotations

import argparse
import json
from pathlib import Path

from runtime.deliverable_production import (
    LocalArtifactToolPresentationRenderer,
    augment_specification_with_commercial_evidence,
    bind_source_register_to_specification,
    build_growth_blueprint_presentation_spec,
    build_quantified_commercial_model,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs" / "calibrations" / "fieldwork-three-business" / "katkin"


def section(text: str, implication: str, refs: list[str]) -> dict:
    return {"diagnosis": text, "implication": implication, "uncertainties": ["First-party performance data remains unavailable."], "evidence_refs": refs}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--node-modules", type=Path, required=True)
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output already exists; example outputs are immutable")
    args.output.mkdir(parents=True)

    founder = json.loads((SOURCE / "founder-argument.json").read_text(encoding="utf-8"))["founder_argument"]
    research = json.loads((SOURCE / "research-case.json").read_text(encoding="utf-8"))
    synthesis = research["strategic_synthesis"]
    artifact = {
        "market_category_diagnosis": section(synthesis["executive_synthesis"], synthesis["commercial_problem"], ["K1", "K6", "K7"]),
        "audience": section(founder["audience_opportunity"]["priority_audience"], founder["audience_opportunity"]["commercial_relevance"], ["K2", "K8", "K9"]),
        "growth_barriers": section(synthesis["commercial_problem"], "Proof must do practical work at trial and transition.", ["K2", "K3", "K9"]),
        "source_of_difference": section("KatKin's scientific ambition and product-learning capability are harder to copy than convenience claims.", "Turn research into a useful decision system.", ["K3", "K5", "K6"]),
        "positioning": section(founder["central_argument"], "Own the decision to start and stay with fresh feeding.", ["K3", "K8", "K9"]),
        "narrative": section("Science becomes useful when it helps a cat parent decide, transition and recognise progress.", "Build proof around the moments where commitment can lapse.", ["K3", "K9"]),
        "growth_opportunity": section(founder["business_opportunity"]["statement"], founder["business_opportunity"]["commercial_consequence"], ["K1", "K3", "K9"]),
        "activation_implications": section("Instrument transition completion before scaling acquisition.", "Test the proof-to-decision journey against conversion and retained feeding.", ["K2", "K9"]),
        "key_strategic_choices": section("Build the decision system before scaling acquisition further.", "The first decision is whether to commission baseline data and verify the study independently.", ["K1", "K3", "K9"]),
        "evidence_and_uncertainty": section("Public evidence supports the direction but not current conversion, transition, retention or margin performance.", "Use indexed sensitivity until first-party baselines are approved.", ["K1", "K2", "K3"]),
    }
    moves = founder["argument_moves"]
    opening = {
        "contract_version": "4.0.0",
        "slides": [
            {"role": "commercial_position_today", "headline": moves[0]["headline"], "body": moves[0]["argument"], "visual_treatment": "Current position with capital, reported scale and first-party inputs to confirm.", "classification": "evidence", "evidence_refs": moves[0]["evidence_refs"], "content": {"baseline": "Reported scale claims; customer economics unavailable", "growth_question": "Which customer decision currently limits retained feeding?"}},
            {"role": "twelve_month_opportunity", "headline": "A proof-to-decision journey could compound three customer behaviours", "body": "Indexed sensitivity shows the effect of 10% more qualified visits, 10% higher first-purchase conversion and 10% more realised revenue per acquired customer. It is not a KatKin forecast.", "visual_treatment": "Indexed baseline 100 against a 133.1 sensitivity for the modelled new-customer cohort.", "classification": "illustrative_scenario", "evidence_refs": ["K2", "K9"], "assumptions": ["Each multiplier is illustrative at 1.10.", "Existing-customer revenue is excluded.", "Replace the index with approved first-party baselines."], "content": {"dominant_gain": "+33.1%", "scope": "modelled new-customer cohort only"}},
            {"role": "where_gains_come_from", "headline": "Better qualification, clearer proof and a supported transition create the gain", "body": moves[2]["argument"], "visual_treatment": "Editable bridge showing the three non-additive mechanisms and their measures.", "classification": "interpretation", "evidence_refs": moves[2]["evidence_refs"], "content": {"levers": [
                {"action": "Clarify who fresh feeding is for", "behaviour": "More qualified visitors start a trial", "commercial_consequence": "Higher first-purchase conversion", "measure": "Qualified visit to trial rate"},
                {"action": "Turn science into decision proof", "behaviour": "More trialists can justify the change", "commercial_consequence": "More completed transitions", "measure": "Trial to subscription conversion"},
                {"action": "Support the feeding transition", "behaviour": "More new customers continue feeding", "commercial_consequence": "More realised revenue per acquired customer", "measure": "Early retained feeding and revenue per acquired customer"},
            ]}},
            {"role": "audience_opportunity", "headline": moves[3]["headline"], "body": founder["audience_opportunity"]["priority_audience"], "visual_treatment": "The trial-to-subscription decision moment with evidence and validation needs.", "classification": "hypothesis", "evidence_refs": moves[3]["evidence_refs"], "assumptions": founder["audience_opportunity"]["validation_required"], "content": {"buying_moment": founder["audience_opportunity"]["commercial_moment"]}},
            {"role": "strategic_direction", "headline": moves[4]["headline"], "body": moves[4]["argument"], "visual_treatment": "One strategic choice, first action and success measure.", "classification": "interpretation", "evidence_refs": moves[4]["evidence_refs"], "content": {"first_action": "Instrument transition completion and independently verify the study", "measure": "Trial-to-subscription conversion and early retained feeding"}},
        ],
    }
    intelligence = {
        "model_type": "new_customer_cohort", "period": "12 months", "population": "new customers acquired during the period", "currency": "INDEX",
        "inputs": [
            {"input_id": "qualified_visits", "value": 100, "status": "illustrative", "source_ids": []},
            {"input_id": "first_purchase_conversion_rate", "value": 1, "status": "illustrative", "source_ids": []},
            {"input_id": "realized_revenue_per_acquired_customer", "value": 1, "status": "illustrative", "source_ids": []},
        ],
        "scenarios": [{"name": "Indexed sensitivity", "qualified_visits_multiplier": 1.1, "conversion_multiplier": 1.1, "revenue_per_customer_multiplier": 1.1, "classification": "illustrative_scenario", "assumptions": ["Equal 10% sensitivities are illustrative only."]}],
        "existing_customer_revenue": {"status": "excluded_from_new_customer_cohort"}, "limitations": ["Not a company forecast.", "No first-party baseline supplied."],
        "production_direction": {
            "brand_name": "KatKin", "fieldwork_opening": opening,
            "layout_content": {
                "market_gap_map": {"x_axis": ["Claims", "Decision proof"], "y_axis": ["Generic fresh", "Cat-specific"], "competitors": [["Fresh category", 32, 42]], "current_position": ["KatKin today", 55, 66], "future_position": ["Decision system", 82, 84], "market_gap": "Useful science at the decision moment", "audience": "Committed cat parents weighing price and routine change", "competitor_miss": "Convenience and ingredient claims are increasingly shared"},
                "customer_evidence_board": {"language_status": "HYPOTHESIS; FIRST-PARTY VALIDATION REQUIRED", "customer_language": ["Is the change worth the price and routine?", "How will I know fresh feeding is working?"], "signals": [["PRICE MECHANICS", "The recurring commitment is material."], ["SCIENCE ASSET", "Comparative evidence exists but needs independent verification."], ["COMPETITION", "Convenience and whole-meat claims are shared."]], "interpretation": "Proof should resolve commitment, not merely create attention."},
                "positioning_map": {"x_axis": ["Brand claim", "Decision aid"], "y_axis": ["Category generic", "Cat-specific"], "positions": [["Today", 52, 68], ["Opportunity", 84, 88]], "territory": "The trusted way to decide, start and stay with fresh feeding"},
                "messaging_territories": {"territories": [["Decide with evidence", "Trial", "Price and proof", "Verified science", "Proof ladder"], ["Transition with confidence", "Onboarding", "Routine change", "Practical guidance", "Transition markers"], ["Recognise progress", "Retention", "Is it working?", "Observed outcomes", "Progress record"]], "verbal_assets": ["Decide with evidence", "Fresh feeding, made observable"], "tone_motion_cues": ["Direct and careful", "Evidence before claim"], "recurring_formats": ["Decision guide", "Transition check-in"]},
                "attention_strategy": {"items": [["NOTICE", "A specific feeding decision"], ["UNDERSTAND", "What the evidence supports"], ["ACT", "One low-risk next step"], ["LEARN", "Cohort result against baseline"]]},
                "closing_mandate": {"lines": ["Build the decision system", "before scaling acquisition", "Measure the transition first."], "next_step": "Instrument trial-to-subscription conversion and independently verify the study before broader-reach investment."},
            },
            "creative_direction": {"title": "Make science useful at the decision moment", "body": "Show proof as a calm, legible guide rather than a dramatic claim.", "takeaway": "Decision proof can make KatKin's scientific ambition commercially useful.", "primary_phrase": "DECIDE WITH EVIDENCE", "secondary_phrase": "then feed with confidence", "principles": [["USEFUL", "Answer a feeding decision"], ["CAREFUL", "Separate evidence from claim"], ["OBSERVABLE", "Show what progress means"]]},
            "slide_overrides": {
                "16": {"content": {"rows": [["POSITION", "Scientific ambition"], ["BENEFIT", "A harder-to-copy source of difference"], ["PROOF GAP", "Effectiveness is not yet proven"], ["EXPRESSION", "Make the choice recognisable"]]}},
                "18": {"content": {"rows": [["POSITION", "Help cat parents decide with evidence"], ["AUDIENCE", "Committed cat parents weighing price and routine"], ["PROMISE", "Make fresh feeding easier to start and sustain"], ["STATUS", "Testable hypothesis — not a proven market fact"]]}},
                "20": {"takeaway": "A clear proof journey can turn scientific ambition into a reason to continue.", "body": "The narrative moves from deciding with evidence to transitioning with confidence and recognising progress."},
                "21": {"takeaway": "One proof ladder can organise trial, transition and retained feeding.", "body": "Build every message around the decision, the supporting evidence and the next useful action."},
            },
        },
    }
    source_entries = []
    for record in research["evidence_records"]:
        source_entries.append({"source_id": record["evidence_id"], "title": record["content"][:72], "publisher": "Source captured in KatKin research case", "date": research["captured_at"][:10], "location": record["source_refs"][0], "classification": record["classification"].lower().replace(" ", "_"), "evidence_refs": [record["evidence_id"]], "applies_to_pages": []})
    source_entries.append({"source_id": "T1", "title": "KatKin FIELDWORK founder argument", "publisher": "Narratiive", "date": research["captured_at"][:10], "location": "governed repository artefact", "classification": "internal_strategy", "evidence_refs": ["T1"], "applies_to_pages": []})
    register = {"entries": source_entries}
    model = build_quantified_commercial_model(intelligence)
    spec = build_growth_blueprint_presentation_spec(artifact, specification_id="fieldwork-v4-katkin-example", source_blueprint_id="katkin-founder-argument", source_blueprint_version=4, workspace_id="narratiive-internal", client_id="katkin-internal", title="FIELDWORK v4 — KatKin", brand_name="KatKin")
    spec = augment_specification_with_commercial_evidence(spec, commercial_model=model, source_register=register, production_direction=intelligence["production_direction"])
    spec, register = bind_source_register_to_specification(spec, register)
    renderer = LocalArtifactToolPresentationRenderer(node=args.node, node_modules=args.node_modules, skill_dir=args.skill_dir, render_script=ROOT / "scripts" / "render_growth_blueprint_deliverable.mjs", pdf_script=ROOT / "scripts" / "build_pdf_from_slides.py", python=args.python)
    pptx, pdf, qa = renderer.render(spec, args.output)
    (args.output / "fieldwork-v4-source-register.json").write_text(json.dumps(register, indent=2) + "\n", encoding="utf-8")
    (args.output / "fieldwork-v4-build-summary.json").write_text(json.dumps({"pptx": str(pptx), "pdf": str(pdf), "visual_qa": qa.to_dict(), "execution_truth": "Tony production components executed locally; Google Slides import is performed separately through the authenticated connector.", "client_release_authorised": False}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pptx": str(pptx), "pdf": str(pdf), "qa": qa.to_dict()}, indent=2))


if __name__ == "__main__":
    main()
