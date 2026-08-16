from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_autonomous_result import TonyPersistentAutonomousResultCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyGroundedNextStepDispatchTests(unittest.TestCase):
    NOW = datetime(2026, 8, 16, 22, 0, tzinfo=timezone.utc)

    def test_explicit_send_approval_dispatches_gmail_and_persists_verified_result(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Path(tmp.name) / "result.json"
        body = "Hi Alex, this is the exact reviewed outreach body and it must be sent unchanged."
        store.write_text(
            json.dumps(
                {
                    "worker": "Claude",
                    "dispatch": {
                        "worker": "Claude",
                        "execution_mode": "autonomous_prepare",
                        "target": {"lead_id": "lead-1", "contact": "Alex Example", "area": "commercial"},
                    },
                    "evidence": {
                        "execution_next_action": "Send the reviewed outreach email to Alex Example via Gmail exactly as reviewed.",
                        "reviewed_outreach_subject": "A sharper growth story for Example Co",
                        "reviewed_outreach_body": body,
                    },
                    "executive_result": "Claude returned a reviewed outreach package.",
                    "verified_at": self.NOW.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        calls: list[dict] = []

        def gmail(dispatch):
            calls.append(dispatch)
            self.assertEqual(dispatch["execution_mode"], "approval_gated_write")
            self.assertTrue(dispatch["approval_granted"])
            self.assertEqual(dispatch["payload"]["subject"], "A sharper growth story for Example Co")
            self.assertEqual(dispatch["payload"]["body"], body)
            return {"sent": True, "message_id": "gmail-123"}

        service = TonyPersistentAutonomousResultCommandService(
            StubCommandService(),
            dispatchers={"Gmail": gmail},
            store_path=store,
            clock=lambda: self.NOW,
        )

        response = service.execute("OK, do that", ())

        self.assertEqual(len(calls), 1)
        self.assertEqual(response.data["execution_status"], "approved_step_verified")
        self.assertEqual(response.data["dispatch_result"]["worker"], "Gmail")
        self.assertEqual(response.data["dispatch_result"]["evidence"]["message_id"], "gmail-123")
        self.assertEqual(response.data["execution_handoff"]["dispatch"]["execution_truth"], "verified_dispatch")
        persisted = json.loads(store.read_text(encoding="utf-8"))
        self.assertEqual(persisted["worker"], "Gmail")
        self.assertEqual(persisted["evidence"]["message_id"], "gmail-123")
        self.assertEqual(persisted["dispatch"]["execution_mode"], "approval_gated_write")


if __name__ == "__main__":
    unittest.main()
