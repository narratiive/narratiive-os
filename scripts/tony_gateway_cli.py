from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.tony_orchestration import (
    HttpGatewayTransport,
    TonyCommand,
    TonyGatewayError,
    TonyOrchestrationAdapter,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one manager-facing Tony action to the Narratiive OS command gateway"
    )
    parser.add_argument("action")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--command-id", default="")
    parser.add_argument("--reviewer-id", default="")
    parser.add_argument("--rationale", default="")
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("NARRATIIVE_GATEWAY_ENDPOINT", "http://127.0.0.1:8787/"),
    )
    parser.add_argument(
        "--api-key-env",
        default="NARRATIIVE_API_KEY",
    )
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is required")

    try:
        payload = json.loads(args.payload_json)
    except json.JSONDecodeError as exc:
        raise SystemExit("--payload-json must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise SystemExit("--payload-json must decode to a JSON object")

    command_id = args.command_id.strip() or f"tony-{uuid4().hex}"
    adapter = TonyOrchestrationAdapter(
        HttpGatewayTransport(
            args.endpoint,
            api_key,
            timeout_seconds=args.timeout_seconds,
        )
    )
    try:
        result = adapter.execute(
            TonyCommand(
                action=args.action,
                workspace_id=args.workspace_id,
                client_id=args.client_id,
                command_id=command_id,
                reviewer_id=args.reviewer_id,
                rationale=args.rationale,
                payload=payload,
            )
        )
    except TonyGatewayError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "retryable": exc.retryable,
                    },
                    "command_id": command_id,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "ok": result.ok,
                "message": result.message,
                "command": result.command,
                "correlation_id": result.correlation_id,
                "command_id": command_id,
                "data": result.data,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
