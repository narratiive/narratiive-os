from __future__ import annotations

import json
import subprocess
import unittest

from scripts.inspect_tony_effective_tools import (
    EXPECTED_NARRATIIVE_TOOLS,
    REQUIRED_ORCHESTRATION_TOOLS,
    inspect_effective_tools,
)


class TonyEffectiveToolSurfaceTests(unittest.TestCase):
    @staticmethod
    def runner(payload: object, returncode: int = 0):
        def run(command, **kwargs):
            assert command[:4] == ["openclaw", "agent", "--agent", "tony"]
            assert "/tools verbose" in command
            assert "--json" in command
            return subprocess.CompletedProcess(command, returncode, stdout=json.dumps(payload), stderr="")
        return run

    def test_current_session_surface_is_ready_when_all_required_tools_are_visible(self):
        tools = sorted(EXPECTED_NARRATIIVE_TOOLS | REQUIRED_ORCHESTRATION_TOOLS)
        payload = {"payloads": [{"text": "Available tools:\n" + "\n".join(tools)}]}
        result = inspect_effective_tools(runner=self.runner(payload))
        self.assertTrue(result["effective_tool_surface_ready"])
        self.assertEqual(set(result["effective_tony_tools"]), set(tools))
        self.assertEqual(result["missing_effective_tony_tools"], [])

    def test_loaded_plugin_but_missing_state_tool_fails_at_policy_boundary(self):
        visible = sorted((EXPECTED_NARRATIIVE_TOOLS | REQUIRED_ORCHESTRATION_TOOLS) - {"narratiive_read_state"})
        payload = {"final": "Available tools: " + ", ".join(visible)}
        result = inspect_effective_tools(runner=self.runner(payload))
        self.assertFalse(result["effective_tool_surface_ready"])
        self.assertEqual(result["failure_stage"], "effective_tool_policy")
        self.assertIn("narratiive_read_state", result["missing_effective_tony_tools"])

    def test_loaded_plugin_but_missing_workflow_tool_fails_at_policy_boundary(self):
        visible = sorted((EXPECTED_NARRATIIVE_TOOLS | REQUIRED_ORCHESTRATION_TOOLS) - {"narratiive_workflow_control"})
        payload = {"final": "Available tools: " + ", ".join(visible)}
        result = inspect_effective_tools(runner=self.runner(payload))
        self.assertFalse(result["effective_tool_surface_ready"])
        self.assertEqual(result["failure_stage"], "effective_tool_policy")
        self.assertIn("narratiive_workflow_control", result["missing_effective_tony_tools"])

    def test_cli_failure_does_not_fall_through_as_healthy(self):
        result = inspect_effective_tools(runner=self.runner({}, returncode=1))
        self.assertFalse(result["effective_tool_surface_ready"])
        self.assertEqual(result["failure_stage"], "effective_tools_inspect")

    def test_invalid_json_fails_closed(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="not-json", stderr="")

        result = inspect_effective_tools(runner=runner)
        self.assertFalse(result["effective_tool_surface_ready"])
        self.assertEqual(result["failure_stage"], "effective_tools_json")


if __name__ == "__main__":
    unittest.main()
