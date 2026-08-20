from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pin_tony_openclaw_model import is_explicit_model_ref, resolved_runtime_model


def smoke_model(model_ref: str, timeout_seconds: int = 90) -> dict[str, Any]:
    if not is_explicit_model_ref(model_ref):
        raise ValueError("model_ref must be an explicit provider/model")
    command = [
        "openclaw", "infer", "model", "run",
        "--model", model_ref,
        "--prompt", "Reply with exactly: pong",
        "--json",
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "model": model_ref,
            "model_inference_ready": False,
            "failure_stage": "model_inference_timeout",
            "timeout_seconds": timeout_seconds,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except OSError as exc:
        return {
            "model": model_ref,
            "model_inference_ready": False,
            "failure_stage": "openclaw_cli_unavailable",
            "error": str(exc)[:300],
        }

    elapsed = round(time.monotonic() - started, 2)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:500]
        return {
            "model": model_ref,
            "model_inference_ready": False,
            "failure_stage": "model_inference_error",
            "exit_code": completed.returncode,
            "elapsed_seconds": elapsed,
            "error": detail,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    return {
        "model": model_ref,
        "model_inference_ready": True,
        "failure_stage": None,
        "elapsed_seconds": elapsed,
        "response_json_valid": payload is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke Tony's resolved OpenClaw model without loading Tony's tools, memory, workspace, or agent loop."
    )
    parser.add_argument("--agent-id", default="tony")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")

    model_ref, source = resolved_runtime_model(args.agent_id)
    report = smoke_model(model_ref, args.timeout_seconds)
    report["agent_id"] = args.agent_id
    report["model_source"] = source
    report["diagnosis"] = (
        "model inference is healthy; a later Tony timeout is in the agent/tool/session path"
        if report["model_inference_ready"]
        else "model inference is not healthy; fix provider/model performance or auth before changing Tony orchestration"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["model_inference_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
