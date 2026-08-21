from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openclaw.tony_agent_gateway import openclaw_config_path, resolve_gateway_bearer
from scripts.check_tony_openclaw_live import DEFAULT_RESPONSES_URL, http_json, response_text


def run_agent_stage_probe(
    *,
    responses_url: str,
    agent_id: str,
    session_key: str,
    gateway_token: str,
    timeout_seconds: float = 45.0,
    transport: Callable[..., Any] = http_json,
) -> dict[str, Any]:
    """Separate Tony's bare conversational agent path from business-state/tool work."""
    headers = {
        "x-openclaw-agent-id": agent_id,
        "x-openclaw-session-key": session_key,
        "x-openclaw-message-channel": "telegram",
    }
    if gateway_token:
        headers["Authorization"] = f"Bearer {gateway_token}"

    baseline_body = {
        "model": f"openclaw/{agent_id}",
        "input": (
            "Tony, reply in one short sentence describing your role at Narratiive. "
            "For this diagnostic, do not inspect live business state or call tools."
        ),
    }
    try:
        baseline_payload = transport(
            responses_url,
            baseline_body,
            headers=headers,
            timeout=timeout_seconds,
        )
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "agent_stage_ready": False,
            "failure_stage": "agent_workspace_or_session",
            "baseline_error": str(exc),
            "baseline_passed": False,
            "business_state_passed": False,
        }

    baseline_text = response_text(baseline_payload)
    baseline_id = str(baseline_payload.get("id") or "").strip() if isinstance(baseline_payload, dict) else ""
    if not baseline_text:
        return {
            "agent_stage_ready": False,
            "failure_stage": "agent_workspace_or_session",
            "baseline_passed": False,
            "business_state_passed": False,
        }

    business_body: dict[str, Any] = {
        "model": f"openclaw/{agent_id}",
        "input": "Morning Tony, anything important?",
    }
    if baseline_id:
        business_body["previous_response_id"] = baseline_id
    try:
        business_payload = transport(
            responses_url,
            business_body,
            headers=headers,
            timeout=timeout_seconds,
        )
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "agent_stage_ready": False,
            "failure_stage": "business_state_or_tool_path",
            "baseline_passed": True,
            "business_state_passed": False,
            "business_state_error": str(exc),
        }

    business_text = response_text(business_payload)
    return {
        "agent_stage_ready": bool(business_text),
        "failure_stage": None if business_text else "business_state_or_tool_path",
        "baseline_passed": True,
        "business_state_passed": bool(business_text),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Tony's OpenClaw agent path in two stages: bare conversation, then live business-state reasoning."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--responses-url", default=os.getenv("TONY_OPENCLAW_RESPONSES_URL", DEFAULT_RESPONSES_URL))
    parser.add_argument("--agent-id", default=os.getenv("TONY_OPENCLAW_AGENT_ID", "tony"))
    parser.add_argument("--session-key", default="narratiive:tony:stage-probe")
    parser.add_argument("--gateway-token", default="")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    config_path = (args.config or openclaw_config_path(os.environ)).expanduser().resolve()
    gateway_token = str(args.gateway_token).strip()
    auth_source = "cli:--gateway-token" if gateway_token else ""
    if not gateway_token:
        gateway_token, auth_source = resolve_gateway_bearer(os.environ, config_path)

    report = run_agent_stage_probe(
        responses_url=args.responses_url,
        agent_id=args.agent_id,
        session_key=args.session_key,
        gateway_token=gateway_token,
        timeout_seconds=args.timeout_seconds,
    )
    report["agent_id"] = args.agent_id
    report["gateway_auth_present"] = bool(gateway_token)
    report["gateway_auth_source"] = auth_source
    report["behaviour_contract"] = "openclaw-workspace"
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report.get("agent_stage_ready"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
