from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


# This script is intentionally supported as a direct path invocation from any cwd.
# Python otherwise places only scripts/ on sys.path, which makes repository packages
# such as openclaw unavailable when Matt runs the documented command directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openclaw.tony_agent_gateway import openclaw_config_path, resolve_gateway_bearer
from scripts.check_tony_openclaw_live import (
    DEFAULT_OLLAMA_TAGS_URL,
    DEFAULT_RESPONSES_URL,
    DEFAULT_SESSION_KEY,
    build_report,
    http_json,
)


def workspace_only_transport(
    url: str,
    body: dict[str, Any] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 120.0,
) -> Any:
    """Mirror production ingress: OpenClaw workspace files own Tony's behaviour."""
    clean_body = dict(body) if body is not None else None
    if clean_body is not None:
        clean_body.pop("instructions", None)
    return http_json(url, clean_body, headers=headers, timeout=timeout)


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
    args = parser.parse_args()

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
        transport=workspace_only_transport,
    )
    report["gateway_auth_present"] = bool(gateway_token)
    report["gateway_auth_source"] = auth_source
    report["behaviour_contract"] = "openclaw-workspace"
    print(json.dumps(report, indent=2, sort_keys=True))
    if not args.inventory_only and not report.get("live_passed", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
