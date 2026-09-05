from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping

from runtime.tony_dispatch_adapters import build_http_dispatchers
from runtime.tony_execution_readiness import REQUIRED_LIVE_WORKERS, build_execution_readiness_report


PROBE_WORKERS = ("Gmail", "Google Calendar", "Google Drive", "Notion", "Fireflies")


def validate(environ: Mapping[str, str], *, required: tuple[str, ...] = PROBE_WORKERS) -> dict[str, Any]:
    readiness = build_execution_readiness_report(environ)
    status_by_worker = {item.worker: item for item in readiness.workers}
    dispatchers = build_http_dispatchers(environ)
    checks: list[dict[str, Any]] = []
    for worker in PROBE_WORKERS:
        configured = status_by_worker[worker].configured
        if not configured:
            checks.append(
                {
                    "worker": worker,
                    "status": "unconfigured",
                    "ok": worker not in required,
                    "missing": list(status_by_worker[worker].missing),
                }
            )
            continue
        dispatcher = dispatchers.get(worker)
        probe = getattr(dispatcher, "probe", None)
        if not callable(probe):
            checks.append({"worker": worker, "status": "probe_unavailable", "ok": False})
            continue
        try:
            evidence = probe()
        except Exception as exc:
            checks.append({"worker": worker, "status": "probe_failed", "ok": False, "reason": str(exc)})
            continue
        verified = (
            isinstance(evidence, dict)
            and evidence.get("verified") is True
            and evidence.get("read_only") is True
            and evidence.get("mutation_count") == 0
            and bool(str(evidence.get("source_id") or "").strip())
        )
        checks.append(
            {
                "worker": worker,
                "status": "verified_read_only" if verified else "unverified_response",
                "ok": verified,
                "source_id": str(evidence.get("source_id") or "") if isinstance(evidence, dict) else "",
            }
        )
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe configured Narratiive business adapters using read-only provider operations."
    )
    parser.add_argument(
        "--require",
        action="append",
        choices=PROBE_WORKERS,
        help="Worker that must be configured and verified. Defaults to all business adapters.",
    )
    args = parser.parse_args()
    required = tuple(args.require) if args.require else PROBE_WORKERS
    report = validate(os.environ, required=required)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
