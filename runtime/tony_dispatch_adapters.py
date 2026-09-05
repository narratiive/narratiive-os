from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import request

from runtime.inbound_leads import CANONICAL_NOTION_LEADS_DATA_SOURCE_ID
from runtime.native_business_adapters import (
    FirefliesDispatcher,
    GmailDispatcher,
    GoogleCalendarDispatcher,
    GoogleDriveDispatcher,
    GoogleOAuthConfig,
    NotionWorkflowProjectionDispatcher,
)
from runtime.tony_claude_api_dispatcher import build_claude_api_dispatcher


SUPPORTED_DISPATCH_WORKERS = (
    "Claude",
    "Fireflies",
    "Gmail",
    "Google Calendar",
    "Google Drive",
    "GitHub",
    "Notion",
    "Replit",
    "n8n",
)


def _env_key(worker: str) -> str:
    return worker.upper().replace(" ", "_").replace("-", "_")


def build_http_dispatchers(
    environ: Mapping[str, str] | None = None,
) -> dict[str, callable]:
    """Build explicitly configured live dispatch handlers.

    HTTP worker endpoints remain the default integration surface. Claude can also be
    explicitly enabled as a direct Anthropic Messages API preparation worker with
    TONY_DISPATCH_CLAUDE_MODE=anthropic_api. Nothing is inferred or enabled merely
    because credentials exist, so Tony remains fail-closed by default.
    """
    env = os.environ if environ is None else environ
    handlers: dict[str, callable] = {}
    for worker in SUPPORTED_DISPATCH_WORKERS:
        key = _env_key(worker)
        url = str(env.get(f"TONY_DISPATCH_{key}_URL", "")).strip()
        if not url:
            continue
        token = str(env.get(f"TONY_DISPATCH_{key}_TOKEN", "")).strip()
        handlers[worker] = _http_handler(url, token)

    claude_mode = str(env.get("TONY_DISPATCH_CLAUDE_MODE", "")).strip().casefold()
    if "Claude" not in handlers and claude_mode == "anthropic_api":
        handlers["Claude"] = build_claude_api_dispatcher(env)

    google_oauth = GoogleOAuthConfig(
        access_token=str(env.get("TONY_GOOGLE_ACCESS_TOKEN", "")).strip(),
        client_id=str(env.get("TONY_GOOGLE_CLIENT_ID", "")).strip(),
        client_secret=str(env.get("TONY_GOOGLE_CLIENT_SECRET", "")).strip(),
        refresh_token=str(env.get("TONY_GOOGLE_REFRESH_TOKEN", "")).strip(),
    )
    native_google = {
        "Gmail": ("google_api", GmailDispatcher),
        "Google Calendar": ("google_api", GoogleCalendarDispatcher),
        "Google Drive": ("google_api", GoogleDriveDispatcher),
    }
    for worker, (mode, factory) in native_google.items():
        if worker in handlers:
            continue
        key = _env_key(worker)
        if (
            str(env.get(f"TONY_DISPATCH_{key}_MODE", "")).strip().casefold() == mode
            and google_oauth.configured
        ):
            if worker == "Google Calendar":
                handlers[worker] = factory(
                    google_oauth,
                    calendar_id=str(env.get("TONY_GOOGLE_CALENDAR_ID", "primary")).strip() or "primary",
                )
            else:
                handlers[worker] = factory(google_oauth)

    if "Notion" not in handlers and str(env.get("TONY_DISPATCH_NOTION_MODE", "")).strip().casefold() == "notion_api":
        token = next(
            (
                str(env.get(name, "")).strip()
                for name in ("NARRATIIVE_NOTION_TOKEN", "NOTION_API_TOKEN", "NOTION_API_KEY", "NOTION_TOKEN")
                if str(env.get(name, "")).strip()
            ),
            "",
        )
        if token:
            handlers["Notion"] = NotionWorkflowProjectionDispatcher(
                token,
                str(env.get("NARRATIIVE_NOTION_LEADS_DATA_SOURCE_ID", "")).strip()
                or CANONICAL_NOTION_LEADS_DATA_SOURCE_ID,
            )

    if "Fireflies" not in handlers and str(env.get("TONY_DISPATCH_FIREFLIES_MODE", "")).strip().casefold() == "fireflies_api":
        api_key = str(env.get("TONY_FIREFLIES_API_KEY") or env.get("FIREFLIES_API_KEY") or "").strip()
        if api_key:
            handlers["Fireflies"] = FirefliesDispatcher(api_key)
    return handlers


def _http_handler(url: str, token: str):
    def dispatch(contract: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"dispatch": contract}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(url, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=30) as response:  # nosec B310 - endpoint is explicit operator config
            raw = response.read().decode("utf-8")
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError("dispatcher response must be a JSON object")
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else payload
        if not evidence:
            raise RuntimeError("dispatcher returned no structured evidence")
        return evidence

    return dispatch
