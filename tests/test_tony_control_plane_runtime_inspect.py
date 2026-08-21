from __future__ import annotations

import json
import subprocess
import unittest

from scripts.inspect_tony_control_plane_runtime import EXPECTED_TOOLS, inspect_runtime


class TonyControlPlaneRuntimeInspectTests(unittest.TestCase):
    @staticmethod
    def runner(payload: object, returncode: int = 0):
        def run(command, **kwargs):
            assert command == ["openclaw", "plugins", "inspect", "narratiive-control-plane", "--runtime", "--json"]
            return subprocess.CompletedProcess(command, returncode, stdout=json.dumps(payload), stderr="")
        return run

    def test_current_three_tool_runtime_is_ready(self):
        payload = {"runtime": {"tools": [{"name": name} for name in sorted(EXPECTED_TOOLS)]}}
        result = inspect_runtime(self.runner(payload))
        self.assertTrue(result["control_plane_runtime_ready"])
        self.assertEqual(set(result["registered_narratiive_tools"]), EXPECTED_TOOLS)
        self.assertEqual(result["missing_narratiive_tools"], [])
        self.assertEqual(result["legacy_narratiive_tools"], [])

    def test_stale_legacy_runtime_fails_closed(self):
        payload = {"runtime": {"tools": [{"name": "narratiive_executive_brief"}, {"name": "narratiive_execute_safe_read"}]}}
        result = inspect_runtime(self.runner(payload))
        self.assertFalse(result["control_plane_runtime_ready"])
        self.assertIn("narratiive_executive_brief", result["legacy_narratiive_tools"])
        self.assertIn("narratiive_read_state", result["missing_narratiive_tools"])
        self.assertEqual(result["failure_stage"], "plugin_runtime_contract")

    def test_inspect_failure_does_not_fall_through_to_conversation(self):
        result = inspect_runtime(self.runner({}, returncode=1))
        self.assertFalse(result["control_plane_runtime_ready"])
        self.assertEqual(result["failure_stage"], "plugin_runtime_inspect")


if __name__ == "__main__":
    unittest.main()
