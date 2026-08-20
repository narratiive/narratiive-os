from __future__ import annotations

import json
import unittest
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
            },
            {"Notion": lambda _dispatch: {"ok": True, "read_only": True, "summary": "record exists"}},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_truth"], "dispatch_attempted_unverified")

    def test_prepare_and_write_cannot_enter_safe_read_executor(self):
        for kind in ("prepare", "write"):
            with self.subTest(kind=kind), self.assertRaises(StructuredSafeReadError):
                execute_payload(
                    {"action": "Do something", "surface": "gmail", "kind": kind},
                    {"Gmail": lambda _dispatch: {}},
                )

    def test_manifest_and_plugin_expose_safe_read_without_native_approval(self):
        manifest = json.loads((PLUGIN / "openclaw.plugin.json").read_text(encoding="utf-8"))
        self.assertIn("narratiive_execute_safe_read", manifest["contracts"]["tools"])
        source = (PLUGIN / "index.js").read_text(encoding="utf-8")
        client = (PLUGIN / "safe-read-client.js").read_text(encoding="utf-8")
        self.assertIn('name: "narratiive_execute_safe_read"', source)
        self.assertIn("executeSafeRead", source)
        self.assertIn("execute_tony_safe_read.py", client)
        self.assertNotIn('event.toolName !== "narratiive_execute_safe_read"', source)

    def test_chief_of_staff_contract_advances_safe_reads_and_keeps_preparation_with_specialists(self):
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("narratiive_execute_safe_read", prompt)
        self.assertIn("may proceed without approval", prompt)
        self.assertIn("reversible internal preparation", prompt)
        self.assertIn("delegate it to the appropriate OpenClaw specialist", prompt)
        self.assertIn("read-only", prompt)


if __name__ == "__main__":
    unittest.main()
