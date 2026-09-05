from __future__ import annotations

import json
import subprocess
from typing import Any, Callable


EXPECTED_TOOLS = {
    "narratiive_read_state",
    "narratiive_execute_safe_read",
    "narratiive_request_action_approval",
    "narratiive_workflow_control",
}
LEGACY_TOOLS = {
    "narratiive_executive_brief",
    "narratiive_current_leads",
    "narratiive_open_work_status",
    "narratiive_recent_execution_status",
    "narratiive_propose_action",
}


def _strings(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.add(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key))
            found.update(_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_strings(item))
    return found


def inspect_runtime(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Prove the Gateway loaded exactly Tony's current Narratiive capability tools."""
    try:
        completed = runner(
            ["openclaw", "plugins", "inspect", "narratiive-control-plane", "--runtime", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"control_plane_runtime_ready": False, "failure_stage": "plugin_runtime_inspect", "error": type(exc).__name__}

    if completed.returncode != 0:
        return {
            "control_plane_runtime_ready": False,
            "failure_stage": "plugin_runtime_inspect",
            "exit_code": completed.returncode,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"control_plane_runtime_ready": False, "failure_stage": "plugin_runtime_json"}

    strings = _strings(payload)
    registered = sorted(tool for tool in EXPECTED_TOOLS | LEGACY_TOOLS if tool in strings)
    missing = sorted(EXPECTED_TOOLS - set(registered))
    legacy = sorted(LEGACY_TOOLS & set(registered))
    ready = not missing and not legacy
    return {
        "control_plane_runtime_ready": ready,
        "registered_narratiive_tools": registered,
        "missing_narratiive_tools": missing,
        "legacy_narratiive_tools": legacy,
        "failure_stage": None if ready else "plugin_runtime_contract",
    }


def main() -> None:
    print(json.dumps(inspect_runtime(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
