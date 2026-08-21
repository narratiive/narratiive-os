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
from scripts.check_tony_openclaw_live import DEFAULT_RESPONSES_URL, http_json, response_text, scenario_passes


def run_specialist_stage_probe(
    *,
    responses_url: str,
    agent_id: str,
    session_key: str,
    gateway_token: str,
    timeout_seconds: float = 45.0,
    transport: Callable[..., Any] = http_json,
) -> dict[str, Any]:
    """Separate durable conversational context from native specialist delegation."""
    headers = {
        "x-openclaw-agent-id": agent_id,
        "x-openclaw-session-key": session_key,
        "x-openclaw-message-channel": "telegram",
    }
    if gateway_token:
        headers["Authorization"] = f"Bearer {gateway_token}"

    seed = {
        "model": f"openclaw/{agent_id}",
        "input": "Tony, remember the diagnostic codename Cedar. Reply briefly to confirm.",
    }
    try:
        seed_payload = transport(responses_url, seed, headers=headers, timeout=timeout_seconds)
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "specialist_stage_ready": False,
            "failure_stage": "durable_context",
            "context_passed": False,
            "specialist_passed": False,
            "context_error": str(exc),
        }

    seed_id = str(seed_payload.get("id") or "").strip() if isinstance(seed_payload, dict) else ""
    if not response_text(seed_payload) or not seed_id:
        return {
            "specialist_stage_ready": False,
            "failure_stage": "durable_context",
            "context_passed": False,
            "specialist_passed": False,
        }

    followup = {
        "model": f"openclaw/{agent_id}",
        "input": "What diagnostic codename did I just give you? Reply with the codename only.",
        "previous_response_id": seed_id,
    }
    try:
        context_payload = transport(responses_url, followup, headers=headers, timeout=timeout_seconds)
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "specialist_stage_ready": False,
            "failure_stage": "durable_context",
            "context_passed": False,
            "specialist_passed": False,
            "context_error": str(exc),
        }

    context_text = response_text(context_payload)
    context_id = str(context_payload.get("id") or "").strip() if isinstance(context_payload, dict) else ""
    if "cedar" not in context_text.casefold() or not context_id:
        return {
            "specialist_stage_ready": False,
            "failure_stage": "durable_context",
            "context_passed": False,
            "specialist_passed": False,
        }

    delegation = {
        "model": f"openclaw/{agent_id}",
        "input": (
            "Ask the Research Agent to inspect its current mission and return one concise sentence about what it is responsible for. "
            "This is internal, read-only work."
        ),
        "previous_response_id": context_id,
    }
    try:
        specialist_payload = transport(responses_url, delegation, headers=headers, timeout=timeout_seconds)
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "specialist_stage_ready": False,
            "failure_stage": "specialist_delegation",
            "context_passed": True,
            "specialist_passed": False,
            "specialist_error": str(exc),
        }

    specialist_text = response_text(specialist_payload)
    specialist_ok = scenario_passes(specialist_text, "specialist_delegation")
    return {
        "specialist_stage_ready": specialist_ok,
        "failure_stage": None if specialist_ok else "specialist_delegation",
        "context_passed": True,
        "specialist_passed": specialist_ok,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Tony's OpenClaw path for durable context first, then native Research delegation."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--responses-url", default=os.getenv("TONY_OPENCLAW_RESPONSES_URL", DEFAULT_RESPONSES_URL))
    parser.add_argument("--agent-id", default=os.getenv("TONY_OPENCLAW_AGENT_ID", "tony"))
    parser.add_argument("--session-key", default="narratiive:tony:specialist-stage-probe")
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

    report = run_specialist_stage_probe(
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
    if not report.get("specialist_stage_ready"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
