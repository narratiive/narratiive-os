from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_RESPONSES_URL = "http://127.0.0.1:18789/v1/responses"
DEFAULT_OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
DEFAULT_SESSION_KEY = "narratiive:tony:live-acceptance"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    text: str


SCENARIOS = (
    Scenario("natural_priority", "Morning Tony, anything important?"),
    Scenario("typo_tolerance", "Whta shoudl I focus on today?"),
    Scenario(
        "specialist_delegation",
        "Ask the Research Agent to inspect its current mission and return one concise sentence about what it is responsible for. This is internal, read-only work.",
    ),
    Scenario("specialist_status", "How's the Research Agent getting on?"),
    Scenario("context_followup", "What did they say?"),
)

_REJECTION_MARKERS = (
    "unknown command",
    "invalid command",
    "command not recognised",
    "command not recognized",
    "unsupported command",
)


def load_openclaw_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("OpenClaw config must be a JSON object")
    return value


def extract_configured_models(config: Mapping[str, Any]) -> list[str]:
    models: set[str] = set()

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                walk(child, key)
            return
        if isinstance(value, str) and "model" in key.casefold() and value.strip():
            models.add(value.strip())

    walk(config)
    return sorted(models)


def extract_ollama_models(payload: Any) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return []
    names: set[str] = set()
    for model in payload["models"]:
        if not isinstance(model, dict):
            continue
        name = str(model.get("name") or model.get("model") or "").strip()
        if name:
            names.add(name)
    return sorted(names)


def response_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def scenario_passes(text: str) -> bool:
    normalized = text.strip().casefold()
    return bool(normalized) and not any(marker in normalized for marker in _REJECTION_MARKERS)


def http_json(url: str, body: dict[str, Any] | None = None, *, headers: Mapping[str, str] | None = None, timeout: float = 120.0) -> Any:
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    data = None
    method = "GET"
    if body is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
        method = "POST"
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc
    return json.loads(raw)


def run_live_probe(
    *,
    responses_url: str,
    agent_id: str,
    session_key: str,
    gateway_token: str,
    transport: Callable[..., Any] = http_json,
) -> list[dict[str, Any]]:
    headers = {
        "x-openclaw-agent-id": agent_id,
        "x-openclaw-session-key": session_key,
        "x-openclaw-message-channel": "telegram",
    }
    if gateway_token:
        headers["Authorization"] = f"Bearer {gateway_token}"

    results: list[dict[str, Any]] = []
    previous_response_id = ""
    for scenario in SCENARIOS:
        body: dict[str, Any] = {
            "model": f"openclaw/{agent_id}",
            "input": scenario.text,
            "instructions": (
                "You are Tony, Narratiive's Chief of Staff. Respond naturally. Use native OpenClaw specialist/session tools when the request requires them. "
                "Do not perform consequential external writes in this acceptance probe and do not invent execution evidence."
            ),
        }
        if previous_response_id:
            body["previous_response_id"] = previous_response_id
        payload = transport(responses_url, body, headers=headers, timeout=120.0)
        text = response_text(payload)
        previous_response_id = str(payload.get("id") or "").strip() if isinstance(payload, dict) else ""
        results.append(
            {
                "name": scenario.name,
                "input": scenario.text,
                "response": text,
                "response_id": previous_response_id,
                "passed": scenario_passes(text),
            }
        )
    return results


def build_report(
    *,
    config_path: Path,
    responses_url: str,
    agent_id: str,
    session_key: str,
    gateway_token: str,
    ollama_tags_url: str,
    live: bool,
    transport: Callable[..., Any] = http_json,
) -> dict[str, Any]:
    config = load_openclaw_config(config_path)
    report: dict[str, Any] = {
        "config_path": str(config_path),
        "configured_models": extract_configured_models(config),
        "responses_url": responses_url,
        "agent_id": agent_id,
    }
    try:
        report["ollama_models"] = extract_ollama_models(transport(ollama_tags_url, None, headers={}, timeout=10.0))
        report["ollama_reachable"] = True
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        report["ollama_models"] = []
        report["ollama_reachable"] = False
        report["ollama_error"] = str(exc)

    if live:
        try:
            scenarios = run_live_probe(
                responses_url=responses_url,
                agent_id=agent_id,
                session_key=session_key,
                gateway_token=gateway_token,
                transport=transport,
            )
            report["scenarios"] = scenarios
            report["live_passed"] = all(item["passed"] for item in scenarios)
        except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            report["scenarios"] = []
            report["live_passed"] = False
            report["live_error"] = str(exc)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Tony's installed OpenClaw model/runtime and run a safe conversational specialist acceptance probe.")
    parser.add_argument("--config", type=Path, default=Path.home() / ".openclaw" / "openclaw.json")
    parser.add_argument("--responses-url", default=os.getenv("TONY_OPENCLAW_RESPONSES_URL", DEFAULT_RESPONSES_URL))
    parser.add_argument("--agent-id", default=os.getenv("TONY_OPENCLAW_AGENT_ID", "tony"))
    parser.add_argument("--session-key", default=os.getenv("TONY_OPENCLAW_ACCEPTANCE_SESSION_KEY", DEFAULT_SESSION_KEY))
    parser.add_argument("--gateway-token", default=os.getenv("OPENCLAW_GATEWAY_TOKEN", ""))
    parser.add_argument("--ollama-tags-url", default=os.getenv("OLLAMA_TAGS_URL", DEFAULT_OLLAMA_TAGS_URL))
    parser.add_argument("--inventory-only", action="store_true", help="Inspect OpenClaw/Ollama model inventory without running live conversation scenarios")
    args = parser.parse_args()

    report = build_report(
        config_path=args.config.expanduser().resolve(),
        responses_url=args.responses_url,
        agent_id=args.agent_id,
        session_key=args.session_key,
        gateway_token=args.gateway_token,
        ollama_tags_url=args.ollama_tags_url,
        live=not args.inventory_only,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not args.inventory_only and not report.get("live_passed", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
