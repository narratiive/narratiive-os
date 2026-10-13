#!/usr/bin/env python3
"""Produce KatKin v5 through Tony from the already-approved Blueprint intelligence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.deliverable_production import (
    _checksum,
    build_quantified_commercial_model,
    commercial_model_quality_checks,
)
from runtime.senior_strategist_review_worker import SeniorStrategistReviewWorker
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from runtime.workflow_quality import (
    blueprint_director_quality_gate,
    growth_blueprint_quality_gate,
    senior_strategist_review_quality_gate,
)


SOURCE_RUN_ID = (
    "katkin-live-acceptance-20260911-gate1-discovery_evidence_to_growth_sprint_proposal-"
    "growth_sprint_to_research_engine-rese-st-strategy_thesis_to_growth_blueprint-53df7bb2fa80df2c3523"
)
SOURCE_ARTIFACT_ID = "artifact-96b831e2aefd67d3-f178c35f1e867c7a"
THESIS_ARTIFACT_ID = "artifact-63f71c6bacf78fe6-92b790e0f4def86f"
RUNTIME_SCOPE = "ef8761045c7e949c8c5a0dc5"


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_new(path: Path, value: object) -> None:
    encoded = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError(f"immutable output already exists with different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def commercial_intelligence() -> dict:
    supporting_slides = [
        {"title": "The proof has to travel in layers", "body": "Lead with one human-readable claim, reveal the published evidence behind it, then offer the full method for those who want to inspect it.", "takeaway": "Evidence becomes an acquisition asset only when it is both quick to grasp and deep enough to inspect.", "layout_type": "evidence_ladder", "citation_labels": ["S2", "T1"], "claim_status": "APPROVED STRATEGY"},
        {"title": "Share gain, not storytelling optimism, drives the upside", "body": "Every 0.25 percentage-point move in a £600m market represents roughly £1.5m in annual revenue before contribution assumptions.", "takeaway": "The scenario model exposes the few assumptions founders should pressure-test, rather than hiding them in a forecast.", "layout_type": "commercial_sensitivity", "citation_labels": ["S8", "S1A"], "claim_status": "ESTIMATE + ASSUMPTION"},
        {"title": "Three numbers unlock an investable business case", "body": "Actual contribution margin, the scoped implementation budget and observed retention are the missing inputs needed to calculate net value and payback.", "takeaway": "Do not approve scaled investment from gross revenue upside alone.", "layout_type": "investment_unlock", "citation_labels": ["T1"], "claim_status": "EVIDENCE GAP"},
        {"title": "The creative system behaves like evidence", "body": "Observation draws the eye; an explicit evidence mark shows what was checked; one coral signal carries the proof across formats.", "takeaway": "Distinctiveness comes from a repeatable behaviour, not decorative variety.", "layout_type": "creative_principles", "citation_labels": ["S2", "T1"], "claim_status": "PROPOSED CREATIVE TERRITORY"},
        {"title": "One proof, translated for each decision environment", "body": "Retail needs instant comprehension, CRM can reveal depth, earned media needs a citable point of view and paid social should create the first moment of intrigue.", "takeaway": "Channel consistency means a shared strategic signal, not identical executions.", "layout_type": "channel_applications", "citation_labels": ["S5", "S6", "T1"], "claim_status": "PROPOSED EXECUTION"},
        {"title": "Test recognition before buying reach", "body": "Run a founder pressure-test, a retail comprehension test and a controlled CRM pilot before moving material media investment.", "takeaway": "Scale only after the proof-led idea improves leading indicators without weakening conversion.", "layout_type": "test_plan", "citation_labels": ["T1"], "claim_status": "PROPOSED TEST PLAN"},
        {"title": "The founder decision is deliberately narrow", "body": "Approve the proof-led strategic territory, commission the missing unit-economics inputs and authorise a bounded retail-and-CRM validation programme.", "takeaway": "A clear decision now preserves options while creating the evidence for a larger commitment.", "layout_type": "founder_decisions", "citation_labels": ["T1"], "claim_status": "HUMAN DECISION REQUIRED"},
    ]
    return {
        "model_id": "katkin-commercial-opportunity-v5",
        "currency": "GBP",
        "period": "incremental annual run-rate at target share",
        "inputs": [
            {
                "input_id": "market_size",
                "label": "Estimated UK cat food market",
                "value": 600000000,
                "unit": "GBP",
                "status": "derived_estimate",
                "source_ids": ["S8"],
                "source_refs": ["ev_5c64#s1"],
                "basis": "Existing Research Engine conversion of the Research & Markets USD 765.91m estimate to approximately GBP 600m.",
            },
            {
                "input_id": "current_market_share_percent",
                "label": "KatKin reported UK cat food market share",
                "value": 2.0,
                "unit": "percent",
                "status": "reported_claim",
                "source_ids": ["S1A"],
                "source_refs": ["ev_5c64#s1"],
                "basis": "The Grocer reporting of KatKin's Series C announcement, December 2025.",
            },
        ],
        "scenario_assumptions": [
            {"name": "Conservative", "target_market_share_percent": 2.25, "contribution_margin_percent": 30},
            {"name": "Base", "target_market_share_percent": 2.50, "contribution_margin_percent": 40},
            {"name": "Ambitious", "target_market_share_percent": 3.00, "contribution_margin_percent": 50},
        ],
        "implementation_cost": {
            "status": "unavailable",
            "value": None,
            "missing_inputs": [
                "approved implementation scope and delivery budget",
                "media reallocation budget",
                "retail production and test costs",
            ],
        },
        "warnings": [
            "This is a market-share scenario model, not a KatKin forecast.",
            "The market size is a Research Engine estimate, not a filed KatKin figure.",
            "Contribution margins are sensitivity assumptions because KatKin margin data was not supplied.",
            "Net value and payback remain unavailable until implementation cost, CAC and retention inputs are supplied.",
        ],
        "production_direction": {
            "brand_name": "KatKin",
            "layout_content": {
                "single_thesis_page": {"signal": "PROOF", "support": "A claim competitors cannot copy in one ad cycle", "brand_name": "KatKin", "platform": "The science cats deserve", "subtitle": "From category claim to category authority", "asset_path": "katkin/hero-cat.png", "image_alt": "Black cat portrait, the KatKin brand subject"},
                "question_frame": {"signal": "ONLY", "support": "Move from awareness as an input to authority as the outcome"},
                "ecosystem_map_of_forces": {"items": [["SAMENESS", "Shared functional language"], ["DISCOVERY", "Organic and AI search shift"], ["ECONOMICS", "Paid creative pressure"], ["MANDATE", "Build a loved brand"]]},
                "sameness_audit": {"eyebrow": "THE HARD PART IS ALREADY DONE", "asset_path": "katkin/nutrition-science.png", "image_alt": "Microscopic nutrition science, the evidential basis of the KatKin strategy"},
                "market_gap_map": {
                    "x_axis": ["CATEGORY CLAIM", "INDEPENDENT PROOF"],
                    "y_axis": ["FUNCTIONAL FEEDING", "BRAND AUTHORITY"],
                    "competitors": [["CATEGORY", 24, 28], ["UNTAMED", 39, 48]],
                    "current_position": ["KATKIN TODAY", 51, 58],
                    "future_position": ["OWNABLE SPACE", 82, 82],
                    "market_gap": "Independent science made easy to feel and easy to inspect",
                },
                "customer_evidence_board": {
                    "signals": [
                        ["CUSTOMER SAYS", "Public reviews surface value and transition friction."],
                        ["SEARCH SHOWS", "Competitors are gaining organic and AI-search visibility."],
                        ["REVIEWS REVEAL", "Strong aggregate satisfaction coexists with price pressure."],
                        ["SOCIAL SHOWS", "High creative volume converges on familiar functional claims."],
                    ],
                    "interpretation": "The opportunity is directional: make proof easier to find without claiming first-party validation.",
                },
                "provocation_page": {"left_label": "WHAT OWNERS SEE", "left_headline": "Confident claims", "left_detail": "Fresh. Real meat. Vet formulated.", "right_label": "WHAT KATKIN CAN PROVE", "right_headline": "Independent science"},
                "audience_reality_split": {"labels": ["COMMITTED DTC", "RETAIL CONVERT", "MAINSTREAM OWNER"]},
                "demand_pool_cards": {"labels": ["COMMITTED DTC", "RETAIL CONVERT", "MAINSTREAM OWNER"]},
                "tension_plus_journey_matrix": {"labels": ["DISCOVERY", "DECISION", "REPEAT"]},
                "we_are_we_are_not_framework": {"rows": [["POSITION", "Proof, not promise"], ["BENEFIT", "Confidence without self-audit"], ["PLATFORM", "The science cats deserve"], ["EXPRESSION", "Visible without personalisation"]]},
                "positioning_map": {
                    "x_axis": ["PROMISE-LED", "PROOF-LED"],
                    "y_axis": ["TRANSACTIONAL", "AUTHORITY-BUILDING"],
                    "positions": [["CATEGORY", 25, 30], ["UNTAMED", 42, 49], ["KATKIN TODAY", 55, 58], ["KATKIN FUTURE", 84, 84]],
                    "territory": "Nutrition proven, not promised",
                },
                "brand_diagnosis_scorecard": {"rows": [["POSITION", "Proof, not promise"], ["BENEFIT", "Confidence without self-audit"], ["PLATFORM", "The science cats deserve"], ["EXPRESSION", "Visible without personalisation"]]},
                "narrative_platform_framework": {"steps": [["TENSION", "The category asks owners to trust claims"], ["SHIFT", "KatKin makes proof the starting point"], ["RESOLUTION", "Independent science carries the decision"]], "banner": "THE SCIENCE CATS DESERVE"},
                "message_architecture": {"master_message": "Nutrition proven, not promised", "proofs": [["PUBLISHED", "Peer-reviewed research"], ["FORMULATED", "Board-Certified Veterinary Nutritionist"], ["MADE", "Vertically integrated production"]]},
                "messaging_territories": {
                    "territories": [
                        ["PROOF, NOT PROMISE", "Credibility", "Distrust of category claims", "Peer-reviewed research", "Coral evidence mark"],
                        ["THE SCIENCE CATS DESERVE", "Emotional meaning", "Nutrition complexity", "Veterinary formulation", "Clinical crop + warm line"],
                        ["VISIBLE CONFIDENCE", "Retail translation", "Shelf-glance uncertainty", "Layered source path", "Observe / mark / signal"],
                    ]
                },
                "attention_strategy": {"items": [["NOTICE", "One coral evidence signal"], ["REMEMBER", "Proof before promise"], ["CONNECT", "Science with intimate cat behaviour"], ["VERIFY", "A readable path to the source"]]},
                "commercial_opportunity_model": {"items": [["EARNED", "A citable point of view"], ["RETAIL", "Premium proof at shelf"], ["CRM", "Segmented confidence"], ["INVESTOR", "Earlier leading signals"]]},
                "channel_role_map": {"rows": [["DTC QUIZ", "Discovery and education", "Personalised"], ["CRM", "Trust and retention", "First party"], ["RETAIL", "Conversion", "Unaided"], ["EARNED / SEARCH", "Scale discovery", "Citable"], ["PAID SOCIAL", "Volume", "Rebalanced"]]},
                "constraint_priority_roadmap": {"phases": [["DAYS 1-30", "Foundation", "Founder pressure-test and evidence audit"], ["DAYS 31-60", "Prove", "Retail translation and CRM pilot"], ["DAYS 61-90", "Scale", "Shift spend only when leading signals move"]]},
                "priority_matrix_plus_measurement_stack": {"rows": [["LEADING / 3-6 MONTHS", "Claim recognition, shelf comprehension, earned search share"], ["LAGGING", "Retail sell-through, blended CAC trend, subscriber retention"], ["COMMERCIAL", "Price realisation versus discount dependency"]]},
                "closing_mandate": {"lines": ["Own the proof.", "Make it easy to feel.", "Then earn the right to scale."], "next_step": "Founder pressure-test and retail translation test"},
            },
            "creative_direction": {
                "title": "Creative direction: make proof visible",
                "body": "Use clinical precision against intimate cat behaviour: cropped observation, visible evidence marks and a single coral signal that draws the eye to proof.",
                "takeaway": "A distinctive world turns the published science into a recognisable visual behaviour, not another nutrition claim.",
                "primary_phrase": "CLINICAL PRECISION",
                "secondary_phrase": "INTIMATE CAT BEHAVIOUR",
                "bridge": "meets",
                "principles": [["OBSERVATION", "Tight crops and watchful eyes"], ["EVIDENCE", "Visible marks that show what was checked"], ["SIGNAL", "One coral cue points to the proof"]],
            },
            "slide_overrides": {
                8: {"takeaway": "KatKin can test an under-leveraged space where independent proof builds brand authority.", "body": "The gap exists because familiar fresh-food claims are easy to copy, while peer-reviewed evidence is harder to reproduce and easier to verify.", "claim_status": "STRATEGIC INTERPRETATION", "citations": ["S2", "S3", "T1"]},
                10: {"body": "The category asks owners to trust confident nutrition claims; KatKin can instead make independent evidence the starting point.", "claim_status": "STRATEGIC INTERPRETATION", "citations": ["S2", "S3", "T1"]},
                13: {"takeaway": "Public customer, search and social signals support a direction, not a settled segment truth.", "body": "Reviews indicate satisfaction alongside price and transition friction; search and social evidence show a crowded field of similar functional claims.", "claim_status": "MIXED VERIFIED FACT + INTERPRETATION", "citations": ["S3", "S4", "S5"]},
                15: {"body": "Three entry points merit testing: health-reset discovery, proof-led comparison and a retail trial that must work without personalisation.", "claim_status": "PROPOSED TEST", "citations": ["S2", "S4", "S6", "T1"], "content": {"items": [["HEALTH RESET", "A health concern prompts active nutrition discovery."], ["PROOF SEEKER", "An owner compares claims and looks for credible evidence."], ["RETAIL TRIAL", "Shelf communication must convert without a personal quiz."]]}},
                18: {"body": "Move from the copyable claim that fresh food is better to a provisional position: cats deserve nutrition validated by independent science, not manufacturer assertion.", "claim_status": "PROPOSED POSITIONING", "citations": ["S2", "S3", "T1"]},
                19: {"takeaway": "Move from familiar promise-led nutrition claims toward proof-led authority, subject to founder and customer validation.", "body": "The axes and plotted positions are strategic hypotheses derived from public competitor claims and KatKin's published evidence.", "claim_status": "POSITIONING HYPOTHESIS", "citations": ["S2", "S3", "T1"]},
                22: {"takeaway": "Three territories let campaigns vary while one evidence behaviour compounds recognition.", "body": "Each territory connects an audience tension to a proof point and a repeatable visual or verbal asset.", "claim_status": "PROPOSED MESSAGING SYSTEM", "citations": ["S2", "S4", "T1"]},
                24: {"takeaway": "Earn memory by repeating one visible evidence signal across every decision context.", "body": "Use a coral evidence mark to attract attention, pair clinical precision with intimate cat behaviour, and always provide a readable route to the source.", "claim_status": "PROPOSED ATTENTION STRATEGY", "citations": ["S2", "S5", "T1"]},
            },
            "supporting_slides": supporting_slides,
        },
    }


def source_register() -> dict:
    return {
        "register_id": "katkin-source-register-v5",
        "entries": [
            {"source_id": "S1A", "title": "Series C, market share and 100m-meal scale report", "publisher": "The Grocer", "date": "December 2025", "location": "thegrocer.co.uk (Series C report)", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s1"], "applies_to_pages": [1, 3, 13, 16]},
            {"source_id": "S1B", "title": "Anikin Ltd statutory accounts and balance sheet", "publisher": "Companies House / Companies in the UK", "date": "FY2023", "location": "companieshouse.gov.uk; companiesintheuk.co.uk", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s1"], "applies_to_pages": [3, 16]},
            {"source_id": "S1C", "title": "Lloyd Page appointed first CMO", "publisher": "Marketing Week", "date": "2025", "location": "marketingweek.com", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s1", "ev_5c64#s5"], "applies_to_pages": [1, 3]},
            {"source_id": "S2", "title": "KatKin heat-damage study and peer-reviewed AGE research", "publisher": "KatKin / Journal of Animal Science", "date": "accessed 11 September 2026", "location": "katkin.com/articles/katkins-heat-damage-study; Journal of Animal Science", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s2"], "applies_to_pages": [1, 4, 5, 9, 10, 11, 12, 13]},
            {"source_id": "S3", "title": "Competitor claims and organic-search comparison", "publisher": "Untamed / Bubblegum Search", "date": "Q3 2025 to September 2026", "location": "untamed.com; bubblegumsearch.com", "classification": "interpretation", "evidence_refs": ["ev_5c64#s3"], "applies_to_pages": [1, 3, 4, 9]},
            {"source_id": "S4", "title": "Pricing, reviews and customer-friction evidence", "publisher": "KatKin / Trustpilot / Cats.com", "date": "accessed 11 September 2026", "location": "katkin.com/our-pricing; uk.trustpilot.com/review/katkin.com; cats.com/katkin-cat-food-review", "classification": "mixed_fact_and_hypothesis", "evidence_refs": ["ev_5c64#s4"], "applies_to_pages": [6, 7, 8, 10, 15]},
            {"source_id": "S5", "title": "Paid-social volume and creative analysis", "publisher": "Motion / Marketing Week", "date": "accessed 11 September 2026", "location": "motionapp.com/library/katkin; marketingweek.com", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s5"], "applies_to_pages": [1, 2, 3, 13, 14]},
            {"source_id": "S6", "title": "Jollyes retail rollout across 80 stores", "publisher": "Pet Business World", "date": "August 2025", "location": "petbusinessworld.co.uk", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s6"], "applies_to_pages": [6, 8, 14, 15]},
            {"source_id": "S7", "title": "Series B strategy and retail partnership context", "publisher": "Active Partners", "date": "30 November 2023", "location": "active.partners", "classification": "verified_fact", "evidence_refs": ["ev_5c64#s7"], "applies_to_pages": [8, 14]},
            {"source_id": "S8", "title": "UK cat food market estimate, USD 765.91m", "publisher": "Research & Markets", "date": "2025 report", "location": "researchandmarkets.com", "classification": "third_party_estimate", "evidence_refs": ["ev_5c64#s1"], "applies_to_pages": [13]},
            {"source_id": "T1", "title": "Approved KatKin Strategy Thesis", "publisher": "Narratiive governed workflow", "date": "September 2026", "location": THESIS_ARTIFACT_ID, "classification": "approved_strategy", "evidence_refs": [
                "thesis:thesis_statement", "thesis:growth_opportunity", "thesis:commercial_ambition",
                "thesis:activation_principles", "thesis:category_choice", "thesis:source_of_difference",
                "thesis:positioning_choice", "thesis:priority_audience", "thesis:narrative_platform",
            ], "applies_to_pages": [1, 2, 9, 10, 11, 12, 17]},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce the governed KatKin v5 Blueprint through Tony")
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=REPOSITORY_ROOT / ".runtime" / "workflow-runtime")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "outputs" / "katkin" / "production-v5")
    parser.add_argument("--approver", default="", help="Authenticated operator identity authorising this exact internal-review render")
    parser.add_argument("--approval-rationale", default="", help="Human-supplied rationale for the checksum-bound production gate")
    args = parser.parse_args()

    root = args.repository_root.resolve()
    scope = args.runtime_root.resolve() / RUNTIME_SCOPE / "artifacts"
    governed = read_object(scope / f"{SOURCE_ARTIFACT_ID}.json")
    thesis_artifact = read_object(scope / f"{THESIS_ARTIFACT_ID}.json")
    approved_thesis = thesis_artifact.get("strategy_thesis")
    candidate = read_object(root / "outputs" / "katkin" / "production-v4" / "katkin-growth-blueprint-v4.json")
    if not isinstance(approved_thesis, dict):
        raise ValueError("approved Strategy Thesis is unavailable")

    source_gate = dict(growth_blueprint_quality_gate(governed))
    director_gate = dict(blueprint_director_quality_gate(candidate))
    candidate_checksum = _checksum(candidate)
    review = SeniorStrategistReviewWorker()({
        **governed,
        **candidate,
        "approved_strategy_thesis": approved_thesis,
        "client_context": {"brand_name": "KatKin"},
        "blueprint_director_output_identity": {"checksum": candidate_checksum},
    })
    review_gate = dict(senior_strategist_review_quality_gate(review))
    if not source_gate.get("passed") or not director_gate.get("passed") or not review_gate.get("passed"):
        raise ValueError("existing KatKin intelligence no longer passes its governed quality gates")

    commercial_inputs = commercial_intelligence()
    model = build_quantified_commercial_model(commercial_inputs)
    model_checks = commercial_model_quality_checks(model)
    if not all(model_checks.values()):
        raise ValueError(f"commercial model failed validation: {model_checks}")
    register = source_register()
    output_dir = args.output_dir.resolve()

    runtime = build_tony_workflow_runtime(
        args.runtime_root.resolve(), workspace_id="narratiive", client_id="katkin"
    )
    run_id = "katkin-growth-blueprint-deliverable-v5-canonical-handoff-r4"
    source_checksum = _checksum(governed)
    inputs = {
        "quality_accepted_growth_blueprint": governed,
        "blueprint_identity": {"artifact_id": SOURCE_ARTIFACT_ID, "version": 1, "checksum": source_checksum},
        "client_context": {"brand_name": "KatKin", "company_name": "KatKin"},
        "evidence_lineage": governed["evidence_lineage"],
        "blueprint_canon": {
            "manifest": "knowledge/blueprint/manifest.json",
            "schema": "knowledge/blueprint/blueprint-schema-v3.md",
            "visual_framework_library": "knowledge/blueprint/visual-framework-library-v1.md",
            "rave_reference_usage": "calibre_only",
        },
        "commercial_intelligence": commercial_inputs,
        "source_register": register,
        "_lineage": {
            "parent_workflow_id": "strategy_thesis_to_growth_blueprint",
            "parent_run_id": SOURCE_RUN_ID,
            "parent_artifact_ids": [SOURCE_ARTIFACT_ID],
            "recovery_status": "immutable_quality_accepted_artifact_adoption",
        },
    }
    if not runtime.runs.repository.exists(run_id):
        runtime.enqueue(
            "growth_blueprint_deliverable_production", run_id, inputs,
            entity_id="katkin", correlation_id=SOURCE_RUN_ID,
        )
    lifecycle = ClientLifecycleRecord(
        client_id="katkin", client_name="KatKin", stage=ClientLifecycleStage.DELIVERY,
        owner="Tony", next_action="Produce v5 for internal founder review",
        evidence=(f"blueprint:{candidate_checksum}",), requires_matt=True,
    )
    state = runtime.runs.load_run(run_id)
    stage = state.stage("produce_growth_blueprint_deliverable")
    if (
        state.status.value == "blocked"
        and str(stage.blocker or state.blocker or "").startswith("worker_unavailable:")
        and not stage.output_artifacts
    ):
        runtime.resume(run_id)
        state = runtime.runs.load_run(run_id)
        stage = state.stage("produce_growth_blueprint_deliverable")
    if state.status.value == "active" and not stage.output_artifacts:
        runtime.advance(run_id, lifecycle)
        state = runtime.runs.load_run(run_id)
        stage = state.stage("produce_growth_blueprint_deliverable")
    if state.status.value == "awaiting_approval" and not stage.output_artifacts:
        if not args.approver.strip() or not args.approval_rationale.strip():
            raise ValueError(
                "Tony is awaiting an authenticated operator approval for the exact v5 candidate; "
                "supply --approver and --approval-rationale through the authorised command boundary"
            )
        runtime.approve(
            run_id,
            approver=args.approver.strip(),
            rationale=args.approval_rationale.strip(),
            approval_binding={
                "artifact_id": SOURCE_ARTIFACT_ID,
                "artifact_version": 1,
                "artifact_checksum": source_checksum,
            },
        )
        runtime.advance(run_id, lifecycle)

    state = runtime.runs.load_run(run_id)
    stage = state.stage("produce_growth_blueprint_deliverable")
    if not stage.output_artifacts:
        raise ValueError(f"Tony v5 production did not return a deliverable: {state.blocker or state.status.value}")
    parent_ids = list(stage.output_artifacts[-1].metadata.get("parent_artifact_ids") or [])
    if parent_ids != [SOURCE_ARTIFACT_ID]:
        raise ValueError(f"Tony production output is not bound to the exact approved parent artefact: {parent_ids}")
    produced = read_object(Path(stage.output_artifacts[-1].location))
    if produced.get("visual_qa", {}).get("status") != "passed":
        raise ValueError(f"Tony rendered-slide review failed: {produced.get('visual_qa')}")

    output_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        Path(str(produced["editable_pptx"])): output_dir / "KatKin-Growth-Blueprint-v5.pptx",
        Path(str(produced["review_pdf"])): output_dir / "KatKin-Growth-Blueprint-v5.pdf",
    }
    rendered_review = Path(str(produced["editable_pptx"])).parent / "rendered-review.json"
    render_receipt = Path(str(produced["editable_pptx"])).parent / "render-receipt.json"
    for source, target in copies.items():
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError(f"immutable deliverable already exists with different content: {target}")
        if not target.exists():
            shutil.copy2(source, target)

    review_output = output_dir / "katkin-growth-blueprint-v5-rendered-review.json"
    ocr_output = output_dir / "katkin-growth-blueprint-v5-rendered-slide-ocr.json"
    rendered_review_record = read_object(rendered_review)
    runtime_ocr = Path(str(rendered_review_record.get("ocr_output") or ""))
    if not runtime_ocr.is_file():
        raise ValueError("rendered review did not preserve its OCR evidence")
    if ocr_output.exists() and hashlib.sha256(ocr_output.read_bytes()).hexdigest() != hashlib.sha256(runtime_ocr.read_bytes()).hexdigest():
        raise ValueError(f"immutable OCR evidence already exists with different content: {ocr_output}")
    if not ocr_output.exists():
        shutil.copy2(runtime_ocr, ocr_output)
    rendered_review_record["ocr_output"] = ocr_output.relative_to(root).as_posix()
    rendered_review_record["pptx_sha256"] = hashlib.sha256((output_dir / "KatKin-Growth-Blueprint-v5.pptx").read_bytes()).hexdigest()
    rendered_review_record["pdf_sha256"] = hashlib.sha256((output_dir / "KatKin-Growth-Blueprint-v5.pdf").read_bytes()).hexdigest()
    write_new(review_output, rendered_review_record)

    execution = {
        **produced["execution_evidence"],
        "upstream_provider_calls_reused": 1,
        "upstream_provider": "anthropic",
        "upstream_model": "claude-sonnet-5",
        "upstream_provider_message_id": "msg_011Cfs5V5A6cuWM5SJPi1w59",
        "upstream_cost_treatment": "sunk prior generation; exact historical price unavailable",
    }
    lineage = {
        "schema_version": "katkin-growth-blueprint.v5",
        "output_id": "katkin-growth-blueprint-v5",
        "output_version": 5,
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_checksum": _checksum(governed),
        "approved_strategy_thesis_artifact_id": THESIS_ARTIFACT_ID,
        "approved_strategy_thesis_checksum": _checksum(thesis_artifact),
        "blueprint_director_candidate_checksum": candidate_checksum,
        "commercial_model_checksum": _checksum(model),
        "source_register_checksum": _checksum(register),
        "prior_blueprint": "katkin-growth-blueprint-v4",
        "recovery_method": "Tony deterministic commercial modelling, source attribution, rendering and rendered-slide review",
        "human_approval_status": "pending_founder_review",
        "external_action_taken": False,
        "production_output_artifact_id": stage.output_artifacts[-1].artifact_id,
        "production_output_parent_artifact_ids": list(stage.output_artifacts[-1].metadata.get("parent_artifact_ids") or []),
    }
    package = {"approved_blueprint": candidate, "commercial_model": model, "source_register": register}
    quality = {
        "governed_intelligence_quality_gate": source_gate,
        "blueprint_director_quality_gate": director_gate,
        "senior_strategist_review_quality_gate": review_gate,
        "commercial_model_quality_checks": model_checks,
        "presentation_quality_gate": stage.quality_result,
        "visual_qa": produced["visual_qa"],
    }
    report = {
        "run_id": run_id,
        "workflow_id": state.workflow_id,
        "workflow_status": state.status.value,
        "approval_status": state.approval_status,
        "all_quality_gates_passed": all((source_gate["passed"], director_gate["passed"], review_gate["passed"], all(model_checks.values()), stage.quality_result.get("passed") is True)),
        "editable_pptx": (output_dir / "KatKin-Growth-Blueprint-v5.pptx").relative_to(root).as_posix(),
        "review_pdf": (output_dir / "KatKin-Growth-Blueprint-v5.pdf").relative_to(root).as_posix(),
        "commercial_model": (output_dir / "katkin-growth-blueprint-v5-commercial-model.json").relative_to(root).as_posix(),
        "source_register": (output_dir / "katkin-growth-blueprint-v5-source-register.json").relative_to(root).as_posix(),
        "execution_evidence": (output_dir / "katkin-growth-blueprint-v5-execution-evidence.json").relative_to(root).as_posix(),
        "unresolved_evidence_gaps": model["implementation_cost"].get("missing_inputs", []) + [
            "actual contribution margin and channel-level unit economics",
            "trial-to-six-month retention and cancellation reasons",
            "retail-to-DTC migration rate",
        ],
        "founder_review_required": True,
        "external_action_taken": False,
    }
    package_path = output_dir / "katkin-growth-blueprint-v5.json"
    model_path = output_dir / "katkin-growth-blueprint-v5-commercial-model.json"
    register_path = output_dir / "katkin-growth-blueprint-v5-source-register.json"
    execution_path = output_dir / "katkin-growth-blueprint-v5-execution-evidence.json"
    quality_path = output_dir / "katkin-growth-blueprint-v5-quality-review.json"
    report_path = output_dir / "katkin-growth-blueprint-v5-delivery-report.json"
    specification_path = output_dir / "katkin-growth-blueprint-v5-presentation-specification.json"
    receipt_path = output_dir / "katkin-growth-blueprint-v5-render-receipt.json"
    write_new(package_path, package)
    write_new(model_path, model)
    write_new(register_path, register)
    write_new(execution_path, execution)
    write_new(quality_path, quality)
    write_new(report_path, report)
    write_new(specification_path, produced["presentation_specification"])
    receipt_record = read_object(render_receipt)
    receipt_record.update({
        "pptx": (output_dir / "KatKin-Growth-Blueprint-v5.pptx").relative_to(root).as_posix(),
        "pdf": (output_dir / "KatKin-Growth-Blueprint-v5.pdf").relative_to(root).as_posix(),
        "specification": specification_path.relative_to(root).as_posix(),
    })
    receipt_record.pop("validation", None)
    write_new(receipt_path, receipt_record)
    bound_files = (
        output_dir / "KatKin-Growth-Blueprint-v5.pptx",
        output_dir / "KatKin-Growth-Blueprint-v5.pdf",
        package_path, model_path, register_path, execution_path, quality_path, report_path,
        review_output, ocr_output, specification_path, receipt_path,
    )
    lineage["deliverables"] = {
        path.name: {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in bound_files
    }
    write_new(output_dir / "katkin-growth-blueprint-v5-lineage.json", lineage)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
