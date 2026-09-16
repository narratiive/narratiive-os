from __future__ import annotations

import json
import os
import unittest
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from runtime.tony_structured_safe_read import StructuredSafeReadError
from scripts.execute_tony_safe_read import execute_payload


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw" / "plugins" / "narratiive-control-plane"


class OpenClawAutonomousSafeReadTests(unittest.TestCase):
    def test_calendar_read_dispatches_without_approval_only_with_read_only_source_evidence(self):
        seen = []

        def calendar(dispatch):
            seen.append(dispatch)
            return {
                "ok": True,
                "read_only": True,
                "event_ids": ["evt-1"],
                "result": ["Thursday 10:00", "Thursday 14:00"],
            }

        result = execute_payload(
            {
                "action": "Check my availability on Thursday.",
                "surface": "calendar",
                "kind": "read",
                "operation": "inspect",
                "target": {"day": "Thursday"},
            },
            {"Google Calendar": calendar},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_truth"], "verified_read")
        self.assertEqual(seen[0]["execution_mode"], "autonomous_read")
        self.assertTrue(seen[0]["eligible"])
        self.assertEqual(seen[0]["state"], "ready_for_autonomous_dispatch")
        self.assertEqual(seen[0]["source"], "openclaw_native_tool")
        self.assertNotIn("approval", seen[0])

    def test_read_that_cannot_prove_no_mutation_remains_unverified(self):
        result = execute_payload(
            {
                "action": "Check my availability on Thursday.",
                "surface": "calendar",
                "kind": "read",
                "operation": "inspect",
            },
            {"Google Calendar": lambda _dispatch: {"ok": True, "event_id": "evt-1"}},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unverified_safe_read")
        self.assertEqual(result["execution_truth"], "dispatch_attempted_unverified")

    def test_read_without_source_identifier_remains_unverified(self):
        result = execute_payload(
            {
                "action": "Read the current Notion record.",
                "surface": "notion",
                "kind": "read",
                "operation": "fetch",
            },
            {"Notion": lambda _dispatch: {"ok": True, "read_only": True, "summary": "record exists"}},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_truth"], "dispatch_attempted_unverified")

    def test_prepare_and_write_cannot_enter_safe_read_executor(self):
        for kind in ("prepare", "write"):
            with self.subTest(kind=kind), self.assertRaises(StructuredSafeReadError):
                execute_payload(
                    {"action": "Do something", "surface": "gmail", "kind": kind, "operation": "inspect"},
                    {"Gmail": lambda _dispatch: {}},
                )

    def test_manifest_and_plugin_expose_safe_read_without_native_approval(self):
        manifest = json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))
        self.assertIn("narratiive_execute_safe_read", manifest["contracts"]["tools"])
        source = (PLUGIN / "index.js").read_text(encoding="utf-8")
        client = (PLUGIN / "safe-read-client.js").read_text(encoding="utf-8")
        self.assertIn('name: "narratiive_execute_safe_read"', source)
        self.assertIn("executeSafeRead", source)
        self.assertIn('"fireflies"', source)
        self.assertIn('ENV_LOADER, envFile, python, "-m", EXECUTOR_MODULE', client)
        self.assertIn('"scripts.execute_tony_safe_read"', client)
        self.assertIn('".config", "narratiive", "runtime.env"', client)
        self.assertIn('".venv", "bin", "python"', client)
        self.assertNotIn('process.env.TONY_PYTHON || "python3"', client)
        self.assertNotIn('stdout.trim() || "{}"', client)
        self.assertNotIn('event.toolName !== "narratiive_execute_safe_read"', source)

    def test_node_client_launches_executor_from_repository_module_path(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        module_uri = (PLUGIN / "safe-read-client.js").resolve().as_uri()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            handle.write("SAFE_READ_TEST=1\n")
            env_file = handle.name
        os.chmod(env_file, 0o600)
        try:
            script = (
                f'import {{ executeSafeRead }} from {json.dumps(module_uri)}; '
                f'const result = await executeSafeRead({json.dumps({"action": "List Gmail inbox", "surface": "gmail", "kind": "read", "operation": "list", "target": {}})}, '
                f'{{python: {json.dumps(sys.executable)}, envFile: {json.dumps(env_file)}}}); console.log(JSON.stringify(result));'
            )
            completed = subprocess.run(
                [node, "--input-type=module", "-e", script],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            os.unlink(env_file)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "dispatcher_unavailable")
        self.assertEqual(result["execution_truth"], "not_dispatched")

    def test_chief_of_staff_contract_advances_safe_reads_and_keeps_preparation_with_specialists(self):
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("narratiive_execute_safe_read", prompt)
        self.assertIn("may proceed without approval", prompt)
        self.assertIn("reversible internal preparation", prompt)
        self.assertIn("delegate it to the appropriate OpenClaw specialist", prompt)
        self.assertIn("read-only", prompt)

    def test_explicit_read_operation_is_required_and_mutation_payloads_fail_closed(self):
        with self.assertRaisesRegex(StructuredSafeReadError, "explicit supported read operation"):
            execute_payload(
                {"action": "Find the email thread", "surface": "gmail", "kind": "read"},
                {"Gmail": lambda _dispatch: {}},
            )
        with self.assertRaisesRegex(StructuredSafeReadError, "mutation-shaped"):
            execute_payload(
                {
                    "action": "Inspect Gmail",
                    "surface": "gmail",
                    "kind": "read",
                    "operation": "search",
                    "target": {"query": "KatKin", "subject": "mutating field"},
                },
                {"Gmail": lambda _dispatch: {}},
            )


if __name__ == "__main__":
    unittest.main()
