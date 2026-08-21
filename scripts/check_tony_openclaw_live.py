from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_RESPONSES_URL = "http://127.0.0.1:18789/v1/responses"
DEFAULT_OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
DEFAULT_SESSION_KEY = "narratiive:tony:live-acceptance"
EXPECTED_AGENT_IDS = ("tony", "research", "strategy", "creative-director", "production", "operations")


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    text: str


SCENARIOS = (
    Scenario("natural_priority", "Morning Tony, anything important?"),
    Scenario("typo_tolerance", "Whta shoudl I focus on today?"),
    Scenario(
        "business_and_specialist_status",
        "What's happening across Narratiive right now, and what are the specialist team doing?",
    ),
    Scenario(
        "specialist_delegation",
        "Ask the Research Agent to inspect its current mission and return one concise sentence about what it is responsible for. This is internal, read-only work.",
    ),
    Scenario("specialist_status", "How's the Research Agent getting on?"),
    Scenario("strategy_status", "And how is the Strategy Agent doing?"),
    Scenario("creative_status", "What about the Creative Director Agent?"),
    Scenario("production_status", "Is the Production Agent blocked on anything?"),
    Scenario("context_followup", "What did they say?"),
    Scenario("contextual_action", "Sort that out for me, but don't send or change anything externally in this test."),
    Scenario("context_revision", "Use Thursday instead. Still don't send or change anything externally."),
    Scenario("execution_truth", "Did it go? Answer only from verified execution evidence; if nothing was sent, say so."),
)

_REJECTION_MARKERS = (
    "unknown command",
    "invalid command",
    "command not recognised",
    "command not recognized",
    "unsupported command",
)

_SPECIALIST_FAILURE_MARKERS = (
    "can't spawn",
    "cannot spawn",
    "unable to spawn",
    "only `tony` exists",
    "only tony exists",
    "requireagentid restriction",
    "blocked by the `requireagentid`",
    "specialists aren't deployed",
    "specialists are not deployed",
    "no active research agent session",
    "nothing's spawned yet",
    "nothing has been spawned",
)

_DELEGATION_NOT_EXECUTED_MARKERS = (
    "want me to spawn",
    "would you like me to spawn",
    "i can spawn",
    "can spawn one",
)

_FALSE_EMPTY_FLEET_MARKERS = (
    "no active projects or sub-agents",
    "no active projects or subagents",
    "no specialists exist",
    "there are no specialists",
)


def load_openclaw_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("OpenClaw config must be a JSON object")
    return value


def _model_ref(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return str(value.get("primary") or "").strip()
    return ""


def configured_primary_model(config: Mapping[str, Any], agent_id: str = "tony") -> tuple[str, str]:
    """Resolve Tony's configured model without guessing provider/catalog fallbacks."""
    agents = config.get("agents")
    if not isinstance(agents, Mapping):
        return "", "unset"

    raw_list = agents.get("list")
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, Mapping) and str(item.get("id") or "").strip() == agent_id:
                model = _model_ref(item.get("model"))
                if model:
                    return model, f"agents.list[{agent_id}].model"

    raw_entries = agents.get("entries")
    if isinstance(raw_entries, Mapping):
        item = raw_entries.get(agent_id)
        if isinstance(item, Mapping):
            model = _model_ref(item.get("model"))
            if model:
                return model, f"agents.entries.{agent_id}.model"

    defaults = agents.get("defaults")
    if isinstance(defaults, Mapping):
        model = _model_ref(defaults.get("model"))
        if model:
            return model, "agents.defaults.model"
    return "", "unset"


def is_explicit_provider_model(model_ref: str) -> bool:
    """OpenClaw recommends an explicit provider/model ref for deterministic selection."""
    provider, separator, model = model_ref.strip().partition("/")
    return bool(separator and provider.strip() and model.strip())


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


def extract_configured_agent_ids(config: Mapping[str, Any]) -> list[str]:
    agents = config.get("agents")
    if not isinstance(agents, Mapping):
        return []
    ids: set[str] = set()
    raw_list = agents.get("list")
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, Mapping):
                agent_id = str(item.get("id") or "").strip()
                if agent_id:
                    ids.add(agent_id)
    raw_entries = agents.get("entries")
    if isinstance(raw_entries, Mapping):
        ids.update(str(key).strip() for key in raw_entries if str(key).strip())
    return sorted(ids)


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


def extract_runtime_agent_ids(payload: Any) -> list[str]:
    items = payload
    if isinstance(payload, dict):
        items = payload.get("agents") or payload.get("items") or payload.get("data") or []
    if not isinstance(items, list):
        return []
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        agent_id = str(item.get("id") or item.get("agentId") or "").strip()
        if agent_id:
            ids.add(agent_id)
    return sorted(ids)


def runtime_agent_ids() -> list[str]:
    try:
        completed = subprocess.run(
            ["openclaw", "agents", "list", "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"openclaw agents list failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:500]
        raise RuntimeError(f"openclaw agents list exited {completed.returncode}: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("openclaw agents list returned invalid JSON") from exc
    return extract_runtime_agent_ids(payload)


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


def scenario_passes(text: str, scenario_name: str = "") -> bool:
    normalized = text.strip().casefold()
    if not normalized or any(marker in normalized for marker in _REJECTION_MARKERS):
        return False
    if scenario_name in {"specialist_delegation", "specialist_status"}:
        if any(marker in normalized for marker in _SPECIALIST_FAILURE_MARKERS):
            return False
        if "research" not in normalized:
            return False
    if scenario_name == "specialist_delegation" and any(marker in normalized for marker in _DELEGATION_NOT_EXECUTED_MARKERS):
        return False
    if scenario_name == "business_and_specialist_status":
        if any(marker in normalized for marker in _FALSE_EMPTY_FLEET_MARKERS):
            return False
        if not all(marker in normalized for marker in ("research", "strategy", "creative", "production", "operations")):
            return False
        if not any(marker in normalized for marker in ("configured", "available", "five specialists", "specialist team")):
            return False
        if not any(marker in normalized for marker in ("child job", "child-job", "delegated", "running", "active work")):
            return False
        if not any(marker in normalized for marker in ("lead", "campaign", "commercial", "mission control", "workstream", "github", "priority")):
            return False
    return True


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
    """Exercise Tony exactly like production: behaviour comes only from the OpenClaw workspace."""
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
                "passed": scenario_passes(text, scenario.name),
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
    agent_inventory: Callable[[], list[str]] = runtime_agent_ids,
) -> dict[str, Any]:
    config = load_openclaw_config(config_path)
    configured_agent_ids = extract_configured_agent_ids(config)
    primary_model, primary_source = configured_primary_model(config, agent_id)
    model_selection_ready = is_explicit_provider_model(primary_model)
    report: dict[str, Any] = {
        "config_path": str(config_path),
        "configured_models": extract_configured_models(config),
        "configured_primary_model": primary_model or None,
        "configured_primary_source": primary_source,
        "model_selection_ready": model_selection_ready,
        "configured_agent_ids": configured_agent_ids,
        "responses_url": responses_url,
        "agent_id": agent_id,
    }
    try:
        runtime_ids = sorted(set(agent_inventory()))
        report["runtime_agent_ids"] = runtime_ids
        report["runtime_fleet_ready"] = set(EXPECTED_AGENT_IDS).issubset(runtime_ids)
    except (RuntimeError, TypeError, ValueError) as exc:
        report["runtime_agent_ids"] = []
        report["runtime_fleet_ready"] = False
        report["runtime_agent_error"] = str(exc)

    try:
        report["ollama_models"] = extract_ollama_models(transport(ollama_tags_url, None, headers={}, timeout=10.0))
        report["ollama_reachable"] = True
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        report["ollama_models"] = []
        report["ollama_reachable"] = False
        report["ollama_error"] = str(exc)

    if live and not model_selection_ready:
        report["scenarios"] = []
        report["live_passed"] = False
        report["live_error"] = (
            "Tony has no explicit provider/model selection. Configure agents.list[tony].model or "
            "agents.defaults.model.primary as provider/model before running conversational acceptance."
        )
        return report

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
            report["live_passed"] = bool(report["runtime_fleet_ready"]) and all(item["passed"] for item in scenarios)
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
