#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import error, request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.acceptance_programme_status import AcceptanceProgrammeStatusBuilder
from runtime.tony_workflow_commands import FileWorkflowCommandBackend
from runtime.workflow_registry import build_narratiive_workflow_registry


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Project Narratiive acceptance status from live evidence.")
    value.add_argument("--scenario-client-id", required=True)
    value.add_argument(
        "--workflow-root",
        type=Path,
        default=REPOSITORY_ROOT / ".runtime" / "workflow-runtime",
    )
    value.add_argument(
        "--deployment-receipt",
        type=Path,
        default=REPOSITORY_ROOT / "runtime-state" / "deployment.json",
    )
    value.add_argument(
        "--conversation-root",
        type=Path,
        default=REPOSITORY_ROOT / ".runtime" / "conversation-work" / "jobs",
    )
    value.add_argument("--format", choices=("json", "text"), default="json")
    return value


def main() -> int:
    args = parser().parse_args()
    deployment = _json_object(args.deployment_receipt)
    conversations = tuple(
        _json_object(path)
        for path in sorted(args.conversation_root.glob("*.json"))
    ) if args.conversation_root.is_dir() else ()
    health = tuple(_probe(endpoint) for endpoint in deployment.get("health_endpoints", []))
    status = AcceptanceProgrammeStatusBuilder(
        build_narratiive_workflow_registry()
    ).build(
        FileWorkflowCommandBackend(args.workflow_root).list_states(),
        scenario_client_id=args.scenario_client_id,
        deployment=deployment,
        service_health=health,
        conversation_work=conversations,
    )
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        _print_text(status)
    return 0


def _json_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unreadable acceptance evidence: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Acceptance evidence must be an object: {path}")
    return value


def _probe(endpoint: str) -> dict:
    name = endpoint.rsplit(":", 1)[-1].split("/", 1)[0]
    try:
        with request.urlopen(endpoint, timeout=3) as response:  # nosec B310 - receipt-owned endpoint
            return {
                "name": name,
                "endpoint": endpoint,
                "healthy": response.status == 200,
                "status_code": response.status,
            }
    except (error.URLError, TimeoutError, ValueError) as exc:
        return {"name": name, "endpoint": endpoint, "healthy": False, "error": type(exc).__name__}


def _print_text(status: dict) -> None:
    checkpoint = status.get("last_verified_checkpoint") or {}
    print(f"Scenario: {status['current_acceptance_scenario']}")
    print(f"Deployed revision: {status['deployed_revision']}")
    print(f"Current stage: {status['current_stage']}")
    print(
        "Last verified checkpoint: "
        f"{checkpoint.get('capability', 'none')}"
        f" ({checkpoint.get('artifact_id', 'no artefact')})"
    )
    print("Capabilities:")
    for item in status["capabilities"]:
        print(f"- {item['capability']}: {item['status']}")
    if status["requires_matt"]:
        print("Requires Matt:")
        for item in status["requires_matt"]:
            print(f"- {item['decision']}")


if __name__ == "__main__":
    raise SystemExit(main())
