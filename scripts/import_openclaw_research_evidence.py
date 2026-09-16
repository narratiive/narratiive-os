#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.research_evidence_import import OpenClawResearchEvidenceImporter


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Promote a completed OpenClaw research session into immutable Narratiive evidence.",
    )
    value.add_argument("--session", type=Path, required=True)
    value.add_argument("--runtime-root", type=Path, default=Path(".runtime/workflow-runtime"))
    value.add_argument("--openclaw-root", type=Path, default=Path.home() / ".openclaw")
    value.add_argument("--workspace-id", required=True)
    value.add_argument("--client-id", required=True)
    value.add_argument("--source-id", required=True)
    value.add_argument("--title", required=True)
    value.add_argument("--approved-by", required=True)
    value.add_argument("--approval-rationale", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    result = OpenClawResearchEvidenceImporter(
        args.runtime_root,
        args.openclaw_root,
    ).import_session(
        args.session,
        workspace_id=args.workspace_id,
        client_id=args.client_id,
        source_id=args.source_id,
        title=args.title,
        approved_by=args.approved_by,
        approval_rationale=args.approval_rationale,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
