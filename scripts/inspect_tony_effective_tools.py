from __future__ import annotations

import json
import subprocess
from typing import Any, Callable


EXPECTED_NARRATIIVE_TOOLS = {
    "narratiive_read_state",
    "narratiive_execute_safe_read",
    "narratiive_request_action_approval",
    "narratiive_workflow_control",
}
REQUIRED_ORCHESTRATION_TOOLS = {
    "agents_list",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
}


def _all_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            found.append(str(key))
            found.extend(_all_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_all_strings(item))
    return found


def inspect_effective_tools(
    agent_id: str = "tony",
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Inspect the tool surface OpenClaw exposes to Tony in a real session.

    Plugin runtime inspection proves registration, but OpenClaw applies profile,
    per-agent, channel and session policy after registration. `/tools verbose` is
    session-scoped, so this catches the exact class of drift where a plugin is loaded
    but Tony still cannot call its tools.
    """
    command = [
        "openclaw",
        "agent",
        "--agent",
        agent_id,
        "--session-key",
        f"narratiive:{agent_id}:effective-tools-probe",
        "--message",
        "/tools verbose",
        "--json",
    ]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "effective_tool_surface_ready": False,
            "failure_stage": "effective_tools_inspect",
            "error": type(exc).__name__,
        }

    if completed.returncode != 0:
        return {
            "effective_tool_surface_ready": False,
            "failure_stage": "effective_tools_inspect",
            "exit_code": completed.returncode,
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "effective_tool_surface_ready": False,
            "failure_stage": "effective_tools_json",
        }

    searchable = "\n".join(_all_strings(payload)).casefold()
    expected = EXPECTED_NARRATIIVE_TOOLS | REQUIRED_ORCHESTRATION_TOOLS
    visible = sorted(tool for tool in expected if tool.casefold() in searchable)
    missing = sorted(expected - set(visible))
    return {
        "effective_tool_surface_ready": not missing,
        "effective_tony_tools": visible,
        "missing_effective_tony_tools": missing,
        "failure_stage": None if not missing else "effective_tool_policy",
    }


def main() -> None:
    result = inspect_effective_tools()
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result.get("effective_tool_surface_ready"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
