from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.diagnose_tony_openclaw_model import configured_primary


def is_explicit_model_ref(value: str) -> bool:
    value = str(value or "").strip()
    if "/" not in value or any(char.isspace() for char in value):
        return False
    provider, model = value.split("/", 1)
    return bool(provider.strip() and model.strip())


def _candidate(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("primary", "resolvedModel", "defaultModel", "model", "id"):
            candidate = _candidate(value.get(key))
            if candidate:
                return candidate
    return ""


def resolved_runtime_model(agent_id: str = "tony") -> tuple[str, str]:
    try:
        completed = subprocess.run(
            ["openclaw", "models", "status", "--agent", agent_id, "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"openclaw models status failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:500]
        raise RuntimeError(f"openclaw models status exited {completed.returncode}: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("openclaw models status returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("openclaw models status returned a non-object payload")

    for key in ("resolvedModel", "model", "primary", "defaultModel"):
        value = _candidate(payload.get(key))
        if value and is_explicit_model_ref(value):
            return value, f"openclaw models status --agent {agent_id}:{key}"
    raise RuntimeError(
        f"OpenClaw did not report an explicit provider/model for agent {agent_id}; refusing to guess or switch providers"
    )


def pin_model(config: dict[str, Any], model_ref: str, agent_id: str = "tony") -> tuple[dict[str, Any], str]:
    if not is_explicit_model_ref(model_ref):
        raise ValueError("model_ref must be an explicit provider/model")
    result = json.loads(json.dumps(config))
    agents = result.setdefault("agents", {})
    if not isinstance(agents, dict):
        raise ValueError("OpenClaw agents config must be an object")

    raw_list = agents.get("list")
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == agent_id:
                current = item.get("model")
                if current:
                    model = dict(current) if isinstance(current, Mapping) else {}
                    model["primary"] = model_ref
                    item["model"] = model
                    return result, f"agents.list[{agent_id}].model.primary"
                break

    defaults = agents.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("OpenClaw agents.defaults config must be an object")
    current_default = defaults.get("model")
    model = dict(current_default) if isinstance(current_default, Mapping) else {}
    model["primary"] = model_ref
    defaults["model"] = model
    return result, "agents.defaults.model.primary"


def build_plan(config_path: Path, agent_id: str = "tony") -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not config_path.exists():
        raise RuntimeError(f"OpenClaw config not found: {config_path}")
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("OpenClaw config must be a JSON object")

    configured, configured_source = configured_primary(loaded, agent_id)
    if is_explicit_model_ref(configured):
        return {
            "agent_id": agent_id,
            "action": "none",
            "configured_model": configured,
            "configured_source": configured_source,
            "reason": "Tony already has an explicit provider/model selection",
        }, None

    resolved, runtime_source = resolved_runtime_model(agent_id)
    updated, target = pin_model(loaded, resolved, agent_id)
    return {
        "agent_id": agent_id,
        "action": "pin",
        "configured_model": configured or None,
        "configured_source": configured_source,
        "resolved_model": resolved,
        "runtime_source": runtime_source,
        "target": target,
        "reason": "Pin the model OpenClaw already resolves for Tony; do not guess or switch provider",
    }, updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pin Tony to the explicit provider/model OpenClaw already resolves for him, without changing providers by guesswork."
    )
    parser.add_argument("--config", type=Path, default=Path.home() / ".openclaw" / "openclaw.json")
    parser.add_argument("--agent-id", default="tony")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()
    plan, updated = build_plan(config_path, args.agent_id)
    plan["config_path"] = str(config_path)
    plan["apply"] = bool(args.apply)

    if args.apply and updated is not None:
        backup = config_path.with_suffix(".json.narratiive-model-backup")
        shutil.copy2(config_path, backup)
        config_path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verified = json.loads(config_path.read_text(encoding="utf-8"))
        model, source = configured_primary(verified, args.agent_id)
        if not is_explicit_model_ref(model):
            shutil.copy2(backup, config_path)
            raise RuntimeError("model pin verification failed; restored the previous OpenClaw config")
        plan["backup_path"] = str(backup)
        plan["verified_model"] = model
        plan["verified_source"] = source

    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.apply and plan["action"] == "pin":
        print("Dry run only. Re-run with --apply to pin the resolved model.")


if __name__ == "__main__":
    main()
