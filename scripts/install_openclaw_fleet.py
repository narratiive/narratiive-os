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
    merged_config = deep_merge(existing_config, fleet)
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
