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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one internal FIELDWORK founder-argument calibration")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    case = json.loads(args.case.read_text(encoding="utf-8"))
    business_id = str(case["business_id"])
    client_name = str(case["client_name"])
    inputs = {
        "evidence_pack": {
            "records": case["evidence_records"],
            "evidence_status": "public_sources_only",
            "captured_at": case["captured_at"],
        },
        "strategic_synthesis": case["strategic_synthesis"],
        "commercial_growth_equation": case["commercial_growth_equation"],
        "approved_growth_sprint_scope": case["approved_growth_sprint_scope"],
        "client_context": {
            "company_name": client_name,
            "relationship": "internal unsolicited calibration; not a client",
            "first_party_data_status": "unavailable",
        },
    }
    runtime = build_tony_workflow_runtime(
        args.output_dir / ".runtime",
        workspace_id="agency-internal",
        client_id=f"{business_id}-fieldwork-calibration",
        environ=None,
    )
    runtime.enqueue(
        "fieldwork_founder_argument_experiment",
        args.run_id,
        inputs,
        entity_id=f"{business_id}-internal-calibration",
        correlation_id="fieldwork-three-business-calibration",
    )
    outcome = runtime.advance(
        args.run_id,
        ClientLifecycleRecord(
            client_id=f"{business_id}-fieldwork-calibration",
            client_name=f"{client_name} internal calibration",
            stage=ClientLifecycleStage.RESEARCH,
            owner="Tony",
            next_action="Review the experimental founder argument",
            evidence=tuple(str(item["evidence_id"]) for item in case["evidence_records"]),
        ),
    )
    state = runtime.runs.load_run(args.run_id)
    stage = state.stage("develop_founder_argument")
    artifact = stage.output_artifacts[-1] if stage.output_artifacts else None
    if artifact is None:
        _write_json(args.output_dir / "quality-result.json", stage.quality_result)
        raise RuntimeError(f"experimental workflow produced no accepted artifact: {stage.quality_result}")
    result = json.loads(Path(artifact.location).read_text(encoding="utf-8"))
    _write_json(args.output_dir / "founder-argument.json", result)
    _write_json(args.output_dir / "quality-result.json", stage.quality_result)
    _write_json(
        args.output_dir / "execution-receipt.json",
        {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "workflow_id": state.workflow_id,
            "run_id": args.run_id,
            "business_id": business_id,
            "status": outcome.status,
            "action": outcome.action,
            "approval_status": state.approval_status,
            "artifact_id": artifact.artifact_id,
            "artifact_checksum": artifact.checksum,
            "provider_message_id": result.get("provider_message_id"),
            "case_sha256": hashlib.sha256(args.case.read_bytes()).hexdigest(),
            "presentation_production_triggered": False,
            "external_action_taken": outcome.external_action_taken,
        },
    )


if __name__ == "__main__":
    main()
