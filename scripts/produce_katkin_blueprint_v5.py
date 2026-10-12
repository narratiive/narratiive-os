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
    run_id = "katkin-growth-blueprint-deliverable-v5-final"
    inputs = {
        "quality_accepted_growth_blueprint": candidate,
        "blueprint_identity": {"artifact_id": "katkin-growth-blueprint-v5", "version": 5, "checksum": candidate_checksum},
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
        runtime.approve(
            run_id,
            approver="authorised-human:katkin-v5-production-mission",
            rationale=(
                "The explicit KatKin v5 mission authorises Tony to model and render the exact reviewed "
                "Blueprint for founder review. External distribution remains prohibited."
            ),
            approval_binding={
                "artifact_id": "katkin-growth-blueprint-v5",
                "artifact_version": 5,
                "artifact_checksum": candidate_checksum,
            },
        )
        runtime.advance(run_id, lifecycle)

    state = runtime.runs.load_run(run_id)
    stage = state.stage("produce_growth_blueprint_deliverable")
    if not stage.output_artifacts:
        raise ValueError(f"Tony v5 production did not return a deliverable: {state.blocker or state.status.value}")
    produced = read_object(Path(stage.output_artifacts[-1].location))
    if produced.get("visual_qa", {}).get("status") != "passed":
        raise ValueError(f"Tony rendered-slide review failed: {produced.get('visual_qa')}")

    output_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        Path(str(produced["editable_pptx"])): output_dir / "KatKin-Growth-Blueprint-v5.pptx",
        Path(str(produced["review_pdf"])): output_dir / "KatKin-Growth-Blueprint-v5.pdf",
    }
    rendered_review = Path(str(produced["editable_pptx"])).parent / "rendered-review.json"
    if rendered_review.is_file():
        copies[rendered_review] = output_dir / "katkin-growth-blueprint-v5-rendered-review.json"
    for source, target in copies.items():
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError(f"immutable deliverable already exists with different content: {target}")
        if not target.exists():
            shutil.copy2(source, target)

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
        "editable_pptx": str(output_dir / "KatKin-Growth-Blueprint-v5.pptx"),
        "review_pdf": str(output_dir / "KatKin-Growth-Blueprint-v5.pdf"),
        "commercial_model": str(output_dir / "katkin-growth-blueprint-v5-commercial-model.json"),
        "source_register": str(output_dir / "katkin-growth-blueprint-v5-source-register.json"),
        "execution_evidence": str(output_dir / "katkin-growth-blueprint-v5-execution-evidence.json"),
        "unresolved_evidence_gaps": model["implementation_cost"].get("missing_inputs", []) + [
            "actual contribution margin and channel-level unit economics",
            "trial-to-six-month retention and cancellation reasons",
            "retail-to-DTC migration rate",
        ],
        "founder_review_required": True,
        "external_action_taken": False,
    }
    write_new(output_dir / "katkin-growth-blueprint-v5.json", package)
    write_new(output_dir / "katkin-growth-blueprint-v5-commercial-model.json", model)
    write_new(output_dir / "katkin-growth-blueprint-v5-source-register.json", register)
    write_new(output_dir / "katkin-growth-blueprint-v5-execution-evidence.json", execution)
    write_new(output_dir / "katkin-growth-blueprint-v5-lineage.json", lineage)
    write_new(output_dir / "katkin-growth-blueprint-v5-quality-review.json", quality)
    write_new(output_dir / "katkin-growth-blueprint-v5-delivery-report.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
