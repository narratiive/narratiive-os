from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FLEET_PATH = REPOSITORY_ROOT / "openclaw" / "openclaw.fleet.json"
ROSTER_PATH = REPOSITORY_ROOT / "openclaw" / "specialists.json"
TONY_TEMPLATE_PATH = REPOSITORY_ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md"
CONTROL_PLANE_PLUGIN_PATH = REPOSITORY_ROOT / "openclaw" / "plugins" / "narratiive-control-plane"
CONTROL_PLANE_PLUGIN_ID = "narratiive-control-plane"


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively apply managed OpenClaw settings while preserving unrelated config."""
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _agent_list(agents: dict[str, Any]) -> list[dict[str, Any]]:
    raw = agents.get("list")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("OpenClaw agents.list must be a list")
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise ValueError("every OpenClaw agents.list entry must be an object with an id")
        result.append(dict(item))
    return result


def _merge_agents(existing_agents: dict[str, Any], managed_agents: dict[str, Any]) -> dict[str, Any]:
    """Merge the managed fleet by agent id while preserving local model/provider choices."""
    existing_without_list = {key: value for key, value in existing_agents.items() if key not in {"list", "entries", "ownership"}}
    managed_without_list = {key: value for key, value in managed_agents.items() if key != "list"}
    merged = deep_merge(existing_without_list, managed_without_list)

    existing_list = _agent_list(existing_agents)
    managed_list = _agent_list(managed_agents)
    existing_by_id = {str(agent["id"]): agent for agent in existing_list}
    managed_ids: set[str] = set()
    merged_list: list[dict[str, Any]] = []

    for managed_agent in managed_list:
        agent_id = str(managed_agent["id"])
        managed_ids.add(agent_id)
        merged_list.append(deep_merge(existing_by_id.get(agent_id, {}), managed_agent))

    for existing_agent in existing_list:
        if str(existing_agent["id"]) not in managed_ids:
            merged_list.append(existing_agent)

    merged["list"] = merged_list
    return merged


def _enable_control_plane_plugin(config: dict[str, Any]) -> None:
    plugins = config.setdefault("plugins", {})
    load = plugins.setdefault("load", {})
    paths = list(load.get("paths") or [])
    plugin_path = str(CONTROL_PLANE_PLUGIN_PATH)
    if plugin_path not in paths:
        paths.append(plugin_path)
    load["paths"] = paths

    entries = plugins.setdefault("entries", {})
    entry = entries.setdefault(CONTROL_PLANE_PLUGIN_ID, {})
    entry["enabled"] = True

    # OpenClaw's plugins.allow is exclusive when present. Preserve every existing
    # trusted plugin and add Narratiive's local plugin rather than replacing policy.
    if isinstance(plugins.get("allow"), list):
        allowed = list(plugins["allow"])
        if CONTROL_PLANE_PLUGIN_ID not in allowed:
            allowed.append(CONTROL_PLANE_PLUGIN_ID)
        plugins["allow"] = allowed


def build_specialist_agents_file(agent: dict[str, Any]) -> str:
    name = str(agent["name"]).strip()
    mission = str(agent["mission"]).strip()
    return (
        f"# {name}\n\n"
        f"Mission: {mission}\n\n"
        "You are a bounded specialist working for Tony, Narratiive's Chief of Staff. "
        "Complete the delegated internal task, state assumptions, and return concise evidence, output and blockers to Tony. "
        "Do not contact clients, send messages, make calendar commitments, mutate authoritative Notion state, or claim external delivery. "
        "A completed specialist task means the internal work is ready for Tony's review; it does not mean an external action occurred.\n"
    )


def build_install_plan(home: Path, existing_config: dict[str, Any]) -> tuple[dict[str, Any], dict[Path, str]]:
    fleet = json.loads(FLEET_PATH.read_text(encoding="utf-8"))
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))

    existing_agents = existing_config.get("agents") or {}
    managed_agents = fleet.get("agents") or {}
    if not isinstance(existing_agents, dict) or not isinstance(managed_agents, dict):
        raise ValueError("OpenClaw agents config must be an object")

    merged_config = deep_merge(existing_config, {key: value for key, value in fleet.items() if key != "agents"})
    merged_config["agents"] = _merge_agents(existing_agents, managed_agents)
    _enable_control_plane_plugin(merged_config)

    workspace_files: dict[Path, str] = {
        home / ".openclaw" / "workspace-tony" / "AGENTS.md": TONY_TEMPLATE_PATH.read_text(encoding="utf-8")
    }
    for agent in roster["specialists"]:
        agent_id = str(agent["id"]).strip()
        workspace_files[home / ".openclaw" / f"workspace-{agent_id}" / "AGENTS.md"] = build_specialist_agents_file(agent)
    return merged_config, workspace_files


def install(*, home: Path, apply: bool) -> dict[str, Any]:
    config_path = home / ".openclaw" / "openclaw.json"
    if config_path.exists():
        existing = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError("existing OpenClaw config must be a JSON object")
    else:
        existing = {}

    merged_config, workspace_files = build_install_plan(home, existing)
    result = {
        "config_path": str(config_path),
        "workspace_files": [str(path) for path in sorted(workspace_files)],
        "control_plane_plugin_path": str(CONTROL_PLANE_PLUGIN_PATH),
        "apply": apply,
        "preserved_top_level_keys": sorted(set(existing) - set(json.loads(FLEET_PATH.read_text(encoding="utf-8")))),
    }
    if not apply:
        return result

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        backup = config_path.with_suffix(".json.narratiive-backup")
        backup.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
        result["backup_path"] = str(backup)

    config_path.write_text(json.dumps(merged_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for path, content in workspace_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Narratiive's bounded Tony OpenClaw fleet without replacing unrelated OpenClaw settings.")
    parser.add_argument("--home", type=Path, default=Path.home(), help="Home directory containing .openclaw")
    parser.add_argument("--apply", action="store_true", help="Write the merged config and managed agent workspace instructions")
    args = parser.parse_args()
    result = install(home=args.home.expanduser().resolve(), apply=args.apply)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not args.apply:
        print("Dry run only. Re-run with --apply after reviewing the plan.")


if __name__ == "__main__":
    main()
