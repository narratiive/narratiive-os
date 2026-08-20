from __future__ import annotations

import unittest
from pathlib import Path

from scripts.execute_tony_structured_action import execute_payload


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw" / "plugins" / "narratiive-control-plane"


class OpenClawApprovedLiveDispatchTests(unittest.TestCase):
    def test_approved_payload_uses_existing_narratiive_executor_and_requires_verified_evidence(self):
        seen = []

        def gmail(dispatch):
            seen.append(dispatch)
            return {"ok": True, "message_id": "msg-live-1", "thread_id": "thread-live-1"}

        result = execute_payload(
            {
                "action": "Send the reviewed reply to Jimmy using Thursday.",
                "surface": "gmail",
                "kind": "write",
                "target": {"contact": "Jimmy", "day": "Thursday"},
            },
            {"Gmail": gmail},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_truth"], "verified_executed")
        self.assertEqual(seen[0]["approval"], "openclaw_allow_once")
        self.assertEqual(seen[0]["target"], {"contact": "Jimmy", "day": "Thursday"})
        self.assertEqual(seen[0]["source"], "openclaw_native_tool")

    def test_worker_text_without_execution_identifier_remains_unverified(self):
        result = execute_payload(
            {
                "action": "Send the reviewed reply to Jimmy.",
                "surface": "gmail",
                "kind": "write",
                "target": {"contact": "Jimmy"},
            },
            {"Gmail": lambda _dispatch: {"ok": True, "summary": "sent"}},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_truth"], "not_verified")

    def test_openclaw_approval_tool_dispatches_after_native_gate_without_phrase_parser(self):
        source = (PLUGIN / "index.js").read_text(encoding="utf-8")
        client = (PLUGIN / "execution-client.js").read_text(encoding="utf-8")
        self.assertIn('api.on("before_tool_call"', source)
        self.assertIn("executeApprovedAction", source)
        self.assertIn("execute_tony_structured_action.py", client)
        self.assertNotIn("yes please", source.lower())
        self.assertNotIn("approved phrase", source.lower())

    def test_tony_contract_keeps_contextual_send_and_did_it_go_on_evidence_path(self):
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("send it", prompt)
        self.assertIn("did it go?", prompt)
        self.assertIn("same tool dispatches only that exact approved action", prompt)
        self.assertIn("verified_executed", prompt)
        self.assertIn("do not call a second conversational approval command", prompt.lower())


if __name__ == "__main__":
    unittest.main()
