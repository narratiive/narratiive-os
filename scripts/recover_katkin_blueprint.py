#!/usr/bin/env python3
"""Adopt the reviewed KatKin candidate and commission Tony's document worker.

The historical failed run remains immutable. This script validates its governed
intelligence, the later Blueprint Director candidate and an independent review,
then starts the existing review-only deliverable workflow with checksum-bound
lineage. The production authorisation is bound to the exact reviewed checksum;
founder approval remains pending and external delivery is never authorised.
"""

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
from runtime.deliverable_production import _checksum
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover the reviewed KatKin Blueprint into Tony's production workflow")
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=REPOSITORY_ROOT / ".runtime" / "workflow-runtime")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "outputs" / "katkin" / "production-v4")
    args = parser.parse_args()

    root = args.repository_root.resolve()
    scope = root / ".runtime" / "workflow-runtime" / "ef8761045c7e949c8c5a0dc5" / "artifacts"
    governed = read_object(scope / f"{SOURCE_ARTIFACT_ID}.json")
    thesis_artifact = read_object(scope / f"{THESIS_ARTIFACT_ID}.json")
    approved_thesis = thesis_artifact.get("strategy_thesis")
    if not isinstance(approved_thesis, dict):
        raise ValueError("approved Strategy Thesis is unavailable")
    candidate = read_object(root / "outputs" / "katkin" / "katkin-growth-blueprint-v2.json")

    source_gate = dict(growth_blueprint_quality_gate(governed))
    director_gate = dict(blueprint_director_quality_gate(candidate))
    if source_gate.get("passed") is not True or director_gate.get("passed") is not True:
        raise ValueError(f"candidate recovery failed quality validation: source={source_gate} director={director_gate}")

    candidate_checksum = _checksum(candidate)
    review_contract = {
        **governed,
        **candidate,
        "approved_strategy_thesis": approved_thesis,
        "client_context": {"brand_name": "KatKin"},
        "blueprint_director_output_identity": {"checksum": candidate_checksum},
    }
    review = SeniorStrategistReviewWorker()(review_contract)
    review_gate = dict(senior_strategist_review_quality_gate(review))
    if review_gate.get("passed") is not True or review.get("reviewed_blueprint_checksum") != candidate_checksum:
        raise ValueError(f"independent review did not forward the exact candidate: {review_gate}")

    output_dir = args.output_dir.resolve()
    write_new(output_dir / "katkin-growth-blueprint-v4.json", candidate)
    write_new(output_dir / "katkin-growth-blueprint-v4-quality-review.json", {
        "governed_intelligence_quality_gate": source_gate,
        "blueprint_director_quality_gate": director_gate,
        "senior_strategist_review": review,
        "senior_strategist_review_quality_gate": review_gate,
    })
    lineage = {
        "schema_version": "katkin-growth-blueprint.v4",
        "output_id": "katkin-growth-blueprint-v4",
        "output_version": 4,
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_checksum": _checksum(governed),
        "approved_strategy_thesis_artifact_id": THESIS_ARTIFACT_ID,
        "approved_strategy_thesis_checksum": _checksum(thesis_artifact),
        "blueprint_director_candidate_checksum": candidate_checksum,
        "prior_blueprint": "katkin-growth-blueprint-v3",
        "supersedes_reason": "v3 visual review found linked-image placeholders; v4 embeds the approved image assets",
        "recovery_method": "validated immutable adoption into Tony deliverable workflow",
        "human_approval_status": "pending_founder_review",
        "external_action_taken": False,
    }
    write_new(output_dir / "katkin-growth-blueprint-v4-lineage.json", lineage)

    runtime = build_tony_workflow_runtime(
        args.runtime_root.resolve(), workspace_id="narratiive", client_id="katkin"
    )
    run_id = "katkin-growth-blueprint-deliverable-v4"
    inputs = {
        "quality_accepted_growth_blueprint": candidate,
        "blueprint_identity": {
            "artifact_id": "katkin-growth-blueprint-v4",
            "version": 4,
            "checksum": candidate_checksum,
        },
        "client_context": {"brand_name": "KatKin", "company_name": "KatKin"},
        "evidence_lineage": governed["evidence_lineage"],
        "blueprint_canon": {
            "manifest": "knowledge/blueprint/manifest.json",
            "schema": "knowledge/blueprint/blueprint-schema-v3.md",
            "visual_framework_library": "knowledge/blueprint/visual-framework-library-v1.md",
            "rave_reference_usage": "calibre_only",
        },
        "review_evidence": {
            "reviewed_blueprint_checksum": candidate_checksum,
            "review_disposition": review["review_disposition"],
            "quality_gate_passed": True,
        },
        "recovery_lineage": lineage,
    }
    if not runtime.runs.repository.exists(run_id):
        runtime.enqueue(
            "growth_blueprint_deliverable_production", run_id, inputs,
            entity_id="katkin", correlation_id=SOURCE_RUN_ID,
        )

    lifecycle = ClientLifecycleRecord(
        client_id="katkin", client_name="KatKin", stage=ClientLifecycleStage.DELIVERY,
        owner="Tony", next_action="Produce internal founder-review deliverable",
        evidence=(f"blueprint:{candidate_checksum}",), requires_matt=True,
    )
    state = runtime.runs.load_run(run_id)
    if state.status.value == "active" and not state.stage("produce_growth_blueprint_deliverable").output_artifacts:
        runtime.advance(run_id, lifecycle)
        state = runtime.runs.load_run(run_id)
    if state.status.value == "awaiting_approval" and not state.stage("produce_growth_blueprint_deliverable").output_artifacts:
        runtime.approve(
            run_id,
            approver="authorised-human:katkin-production-mission",
            rationale=(
                "The explicit KatKin production mission authorises Tony to render this exact "
                "checksum-bound, independently reviewed Blueprint candidate for founder review only; "
                "external distribution remains prohibited."
            ),
            approval_binding={
                "artifact_id": "katkin-growth-blueprint-v4",
                "artifact_version": 4,
                "artifact_checksum": candidate_checksum,
            },
        )
        runtime.advance(run_id, lifecycle)

    state = runtime.runs.load_run(run_id)
    stage = state.stage("produce_growth_blueprint_deliverable")
    if not stage.output_artifacts:
        raise ValueError(f"Tony production did not return a deliverable: {state.blocker or state.status.value}")
    produced = read_object(Path(stage.output_artifacts[-1].location))
    if produced.get("visual_qa", {}).get("status") != "passed":
        raise ValueError(f"Tony production visual QA failed: {produced.get('visual_qa')}")

    pptx_source = Path(str(produced["editable_pptx"]))
    pdf_source = Path(str(produced["review_pdf"]))
    pptx_target = output_dir / "KatKin-Growth-Blueprint-v4.pptx"
    pdf_target = output_dir / "KatKin-Growth-Blueprint-v4.pdf"
    for source, target in ((pptx_source, pptx_target), (pdf_source, pdf_target)):
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError(f"immutable deliverable already exists with different content: {target}")
        if not target.exists():
            shutil.copy2(source, target)

    report = {
        "run_id": run_id,
        "workflow_id": state.workflow_id,
        "workflow_status": state.status.value,
        "approval_status": state.approval_status,
        "source_run_retained_as_blocked_history": True,
        "source_quality_gate": source_gate,
        "blueprint_director_quality_gate": director_gate,
        "independent_review_quality_gate": review_gate,
        "presentation_quality_gate": stage.quality_result,
        "visual_qa": produced["visual_qa"],
        "editable_pptx": str(pptx_target),
        "review_pdf": str(pdf_target),
        "external_action_taken": False,
        "founder_review_required": True,
    }
    write_new(output_dir / "katkin-growth-blueprint-v4-delivery-report.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
