from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_workflow_runtime import build_tony_workflow_runtime


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _runtime_pack(frozen: dict[str, Any]) -> dict[str, Any]:
    return {
        "records": [
            {
                "evidence_id": str(source["source_id"]),
                "classification": "VERIFIED EXTERNAL",
                "captured_at": source.get("captured_at"),
                "status": source.get("status"),
                "content_sha256": source.get("sha256"),
                "content": source.get("content"),
            }
            for source in frozen.get("sources") or []
            if isinstance(source, dict)
        ],
        "comparison_pack_id": frozen.get("pack_id"),
        "evidence_status": frozen.get("evidence_status"),
    }


def _inputs(frozen: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_pack": _runtime_pack(frozen),
        "strategic_synthesis": {
            "executive_synthesis": (
                "Rave has assembled approachable speciality coffee, recurring purchase routes, education, "
                "wholesale service and products for different levels of interest. The frozen public evidence "
                "does not show that customers understand these pieces as one journey or that any route has "
                "superior economics. The useful strategic question is therefore how Rave can convert the moment "
                "someone upgrades from supermarket coffee into confident choice, early repeat and later discovery. "
                "The answer must remain a hypothesis until Rave supplies channel conversion, repeat, contribution "
                "and cohort evidence. Public claims also require current revalidation before external use."
            ),
            "commercial_problem": (
                "Rave has many credible entry and retention assets, but the public experience does not yet prove "
                "which connected customer progression creates more valuable repeat behaviour."
            ),
            "growth_opportunity": (
                "Make the upgrade moment easier to enter and navigate, then measure whether first choice, early "
                "repeat and guided progression improve contribution before scaling acquisition."
            ),
            "implications": [
                "Treat the upgrader as a testable commercial moment rather than a finished persona.",
                "Use a transparent lever model until internal economics replace every open variable.",
                "Require proof and operational reliability before scaling any acquisition route.",
            ],
        },
        "commercial_growth_equation": {
            "commercial_ambition": "Increase the value created by each qualified customer relationship over twelve months.",
            "current_state": "Public evidence shows multiple purchase routes but no verified channel or cohort economics.",
            "growth_gap": "Rave cannot yet show which entry route produces stronger repeat purchase and contribution.",
            "growth_logic": "Improve qualified entry, first choice, early repeat and progression, then scale only proven steps.",
            "growth_levers": [
                "qualified reach at the upgrade moment",
                "first purchase conversion",
                "early repeat behaviour",
                "progression into greater value",
            ],
            "assumptions": [
                "The upgrader audience remains a hypothesis.",
                "No numerical forecast is authorised without internal baselines.",
            ],
        },
        "approved_growth_sprint_scope": {
            "status": "internal_experiment_only",
            "question": "How can Rave turn the upgrade moment into a more valuable customer progression?",
            "constraints": [
                "No Rave contact",
                "No invented financials",
                "No presentation production",
                "No external action",
            ],
        },
        "client_context": {
            "company_name": "Rave Coffee",
            "relationship": "internal unsolicited exercise; not a client",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-pack", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    frozen = json.loads(args.research_pack.read_text(encoding="utf-8"))
    inputs = _inputs(frozen)
    runtime_root = args.output_dir / ".runtime"
    runtime = build_tony_workflow_runtime(
        runtime_root,
        workspace_id="agency-internal",
        client_id="rave-quality-benchmark",
        environ=None,
    )
    run_id = "rave-fieldwork-founder-argument-20261018-v3"
    runtime.enqueue(
        "fieldwork_founder_argument_experiment",
        run_id,
        inputs,
        entity_id="rave-internal-benchmark",
        correlation_id="issue-477-fieldwork-quality-repair",
    )
    outcome = runtime.advance(
        run_id,
        ClientLifecycleRecord(
            client_id="rave-quality-benchmark",
            client_name="Rave Coffee internal benchmark",
            stage=ClientLifecycleStage.RESEARCH,
            owner="Tony",
            next_action="Review the experimental founder argument",
            evidence=("internal:issue-477-rave-frozen-pack",),
        ),
    )
    state = runtime.runs.load_run(run_id)
    stage = state.stage("develop_founder_argument")
    artifact = stage.output_artifacts[-1] if stage.output_artifacts else None
    if artifact is None:
        raise RuntimeError(f"experimental workflow produced no accepted artifact: {stage.quality_result}")
    result = json.loads(Path(artifact.location).read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "experimental-founder-argument.json", result)
    _write_json(args.output_dir / "experimental-quality-result.json", stage.quality_result)
    _write_json(
        args.output_dir / "experimental-execution-receipt.json",
        {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "workflow_id": state.workflow_id,
            "run_id": run_id,
            "status": outcome.status,
            "action": outcome.action,
            "approval_status": state.approval_status,
            "artifact_id": artifact.artifact_id,
            "artifact_checksum": artifact.checksum,
            "research_pack_sha256": hashlib.sha256(args.research_pack.read_bytes()).hexdigest(),
            "presentation_production_triggered": False,
            "external_action_taken": outcome.external_action_taken,
        },
    )


if __name__ == "__main__":
    main()
