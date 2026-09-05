from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.real_evidence_pilot import (
    PilotAuditLedger,
    PilotManifest,
    PilotValidationError,
    inspect_pilot,
)
from runtime.tony_workflow_commands import FileWorkflowCommandBackend


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight or inspect one controlled real-evidence Narratiive pilot.")
    parser.add_argument("command", choices=("preflight", "status"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--ledger-root",
        type=Path,
        default=REPOSITORY_ROOT / ".runtime" / "pilot-audit",
    )
    parser.add_argument(
        "--workflow-root",
        type=Path,
        default=Path(os.getenv("TONY_WORKFLOW_RUNTIME_PATH", REPOSITORY_ROOT / ".runtime" / "workflows")),
    )
    args = parser.parse_args()
    try:
        manifest = PilotManifest.load(args.manifest)
        if args.command == "preflight":
            recorded = PilotAuditLedger(args.ledger_root).record_preflight(manifest)
            report = {
                "ok": True,
                "pilot_id": manifest.pilot_id,
                "status": recorded["status"],
                "event_id": recorded["event_id"],
                "workflow_count": len(manifest.workflow_ids),
                "evidence_source_count": len(manifest.evidence_sources),
                "external_actions_allowed": False,
            }
        else:
            states = FileWorkflowCommandBackend(args.workflow_root).list_states()
            acceptance = inspect_pilot(manifest, states)
            report = {"ok": acceptance["ready"], **acceptance}
    except PilotValidationError as exc:
        report = {"ok": False, "error_code": str(exc)}
    except RuntimeError:
        report = {"ok": False, "error_code": "pilot_workflow_state_unavailable"}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
