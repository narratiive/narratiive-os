from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


# This script is intentionally supported as a direct path invocation from any cwd.
# Python otherwise places only scripts/ on sys.path, which makes repository packages
# such as openclaw unavailable when the documented command is run directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openclaw.tony_agent_gateway import openclaw_config_path, resolve_gateway_bearer
from scripts.check_tony_openclaw_live import (
    DEFAULT_OLLAMA_TAGS_URL,
    DEFAULT_RESPONSES_URL,
    DEFAULT_SESSION_KEY,
    build_report,
)
from scripts.pin_tony_openclaw_model import resolved_runtime_model
from scripts.smoke_tony_openclaw_model import smoke_model


def diagnose_timeout_boundary(
    report: dict[str, Any],
    agent_id: str,
    *,
    timeout_seconds: int = 90,
    resolver: Callable[[str], tuple[str, str]] = resolved_runtime_model,
    smoke: Callable[[str, int], dict[str, Any]] = smoke_model,
) -> dict[str, Any]:
    """Classify a live Tony timeout without changing provider, model, tools, or agent timeout."""
    if report.get("live_passed") or not report.get("model_selection_ready"):
        return report
    live_error = str(report.get("live_error") or "").casefold()
    if "timed out" not in live_error and "timeout" not in live_error:
        return report

    try:
        model_ref, model_source = resolver(agent_id)
    except (RuntimeError, ValueError, OSError):
        report["failure_boundary"] = "model_resolution"
        report["failure_diagnosis"] = (
            "Tony timed out and the active provider/model could not be resolved safely; do not guess or switch providers."
        )
        report["model_smoke"] = {
            "model_inference_ready": False,
            "failure_stage": "model_resolution_error",
        }
        return report

    result = smoke(model_ref, timeout_seconds)
    safe_keys = (
        "model",
        "model_inference_ready",
        "failure_stage",
        "timeout_seconds",
        "elapsed_seconds",
        "exit_code",
        "response_json_valid",
    )
    safe_result = {key: result[key] for key in safe_keys if key in result}
    safe_result["model_source"] = model_source
    report["model_smoke"] = safe_result

    if result.get("model_inference_ready"):
        report["failure_boundary"] = "agent_tool_session"
        report["failure_diagnosis"] = (
            "Raw model inference is healthy; Tony's timeout is later in the workspace/tool/session/specialist orchestration path."
        )
    else:
        report["failure_boundary"] = "model_provider"
        report["failure_diagnosis"] = (
            "Raw model inference also failed; fix provider/model health, auth, or provider-scoped timeout before changing Tony orchestration."
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Tony's live OpenClaw acceptance probe using the active Gateway auth configuration."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--responses-url", default=os.getenv("TONY_OPENCLAW_RESPONSES_URL", DEFAULT_RESPONSES_URL))
    parser.add_argument("--agent-id", default=os.getenv("TONY_OPENCLAW_AGENT_ID", "tony"))
    parser.add_argument("--session-key", default=os.getenv("TONY_OPENCLAW_ACCEPTANCE_SESSION_KEY", DEFAULT_SESSION_KEY))
    parser.add_argument("--gateway-token", default="", help="Optional explicit bearer override; normally resolved automatically")
    parser.add_argument("--ollama-tags-url", default=os.getenv("OLLAMA_TAGS_URL", DEFAULT_OLLAMA_TAGS_URL))
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument(
        "--model-smoke-timeout-seconds",
        type=int,
        default=90,
        help="Bounded raw-model diagnostic used only when the full Tony agent run times out",
    )
    args = parser.parse_args()
    if args.model_smoke_timeout_seconds < 1:
        parser.error("--model-smoke-timeout-seconds must be positive")

    config_path = (args.config or openclaw_config_path(os.environ)).expanduser().resolve()
    gateway_token = str(args.gateway_token).strip()
    auth_source = "cli:--gateway-token" if gateway_token else ""
    if not gateway_token:
        gateway_token, auth_source = resolve_gateway_bearer(os.environ, config_path)

    report = build_report(
        config_path=config_path,
        responses_url=args.responses_url,
        agent_id=args.agent_id,
        session_key=args.session_key,
        gateway_token=gateway_token,
        ollama_tags_url=args.ollama_tags_url,
        live=not args.inventory_only,
    )
    if not args.inventory_only:
        diagnose_timeout_boundary(
            report,
            args.agent_id,
            timeout_seconds=args.model_smoke_timeout_seconds,
        )
    report["gateway_auth_present"] = bool(gateway_token)
    report["gateway_auth_source"] = auth_source
    report["behaviour_contract"] = "openclaw-workspace"
    print(json.dumps(report, indent=2, sort_keys=True))
    if not args.inventory_only and not report.get("live_passed", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
