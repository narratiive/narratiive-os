from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_tony_openclaw_live import extract_ollama_models, http_json


def _model_ref(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return str(value.get("primary") or "").strip()
    return ""


def configured_primary(config: Mapping[str, Any], agent_id: str = "tony") -> tuple[str, str]:
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


def runtime_model_status(agent_id: str = "tony") -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["openclaw", "models", "status", "--agent", agent_id, "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "error": f"openclaw models status failed: {exc}"}
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:500]
        return {"available": False, "error": f"openclaw models status exited {completed.returncode}: {detail}"}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"available": False, "error": "openclaw models status returned invalid JSON"}
    if not isinstance(payload, dict):
        return {"available": False, "error": "openclaw models status returned a non-object payload"}

    # Keep diagnostics credential-safe: expose only model/provider selection fields.
    allowed = ("model", "primary", "defaultModel", "resolvedModel", "provider", "fallbacks")
    safe = {key: payload[key] for key in allowed if key in payload}
    return {"available": True, "status": safe, "agent_id": agent_id}


def build_report(config_path: Path, agent_id: str = "tony") -> dict[str, Any]:
    config: dict[str, Any] = {}
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("OpenClaw config must be a JSON object")
        config = loaded

    primary, source = configured_primary(config, agent_id)
    report: dict[str, Any] = {
        "agent_id": agent_id,
        "configured_primary_model": primary or None,
        "configured_primary_source": source,
        "runtime_model_status": runtime_model_status(agent_id),
    }
    try:
        payload = http_json("http://127.0.0.1:11434/api/tags", None, headers={}, timeout=10.0)
        report["ollama_reachable"] = True
        report["ollama_models"] = extract_ollama_models(payload)
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        report["ollama_reachable"] = False
        report["ollama_models"] = []
        report["ollama_error"] = str(exc)

    report["selection_explicit"] = bool(primary)
    report["diagnosis"] = (
        "Tony has an explicit configured model. Diagnose provider latency before changing model selection."
        if primary
        else "Tony has no explicit configured primary model. OpenClaw may be falling back to provider/catalog order; pin Tony's resolved provider/model explicitly before tuning timeouts or switching to local Ollama."
    )
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose Tony's effective OpenClaw model selection without exposing credentials.")
    parser.add_argument("--config", type=Path, default=Path.home() / ".openclaw" / "openclaw.json")
    parser.add_argument("--agent-id", default="tony")
    args = parser.parse_args()
    print(json.dumps(build_report(args.config.expanduser().resolve(), args.agent_id), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
