from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import request


SUPPORTED_DISPATCH_WORKERS = (
    "Claude",
    "Gmail",
    "Google Calendar",
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
    """Build live dispatch handlers only for explicitly configured worker endpoints.

    Each endpoint receives Tony's pre-authorised dispatch contract as JSON and must
    return a non-empty JSON object containing evidence. No endpoint is inferred or
    enabled by default, so the autonomy decision remains fail-closed.
    """
    env = environ or os.environ
    handlers: dict[str, callable] = {}
    for worker in SUPPORTED_DISPATCH_WORKERS:
        key = _env_key(worker)
        url = str(env.get(f"TONY_DISPATCH_{key}_URL", "")).strip()
        if not url:
            continue
        token = str(env.get(f"TONY_DISPATCH_{key}_TOKEN", "")).strip()
        handlers[worker] = _http_handler(url, token)
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
