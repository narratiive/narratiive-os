from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from runtime.tony_dispatch_adapters import build_http_dispatchers
from runtime.tony_structured_action_execution import (
    StructuredActionExecutionError,
    TonyStructuredActionExecutor,
)


def execute_payload(payload: Mapping[str, Any], dispatchers: Mapping[str, callable] | None = None) -> dict[str, Any]:
    bounded = {
        "action": payload.get("action"),
        "surface": payload.get("surface"),
        "kind": payload.get("kind"),
        "target": payload.get("target") if isinstance(payload.get("target"), dict) else {},
        "approval": "openclaw_allow_once",
    }
    executor = TonyStructuredActionExecutor(dispatchers if dispatchers is not None else build_http_dispatchers())
    return executor.execute(bounded)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        result = execute_payload(payload)
    except (ValueError, TypeError, json.JSONDecodeError, StructuredActionExecutionError) as exc:
        result = {
            "ok": False,
            "status": "invalid_approved_action",
            "error": str(exc),
            "execution_truth": "not_dispatched",
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "approved_action_executor_failed",
            "error": str(exc),
            "execution_truth": "not_verified",
        }
    sys.stdout.write(json.dumps(result, sort_keys=True))
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
