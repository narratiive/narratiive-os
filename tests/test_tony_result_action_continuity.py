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

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, command, objects):
        self.calls.append(command)
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyResultActionContinuityTests(unittest.TestCase):
    NOW = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)

    def _service(self, evidence: dict) -> tuple[TonyPersistentAutonomousResultCommandService, StubCommandService]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "result.json"
        path.write_text(
            json.dumps(
                {
                    "worker": "Gmail",
                    "dispatch": {
                        "worker": "Gmail",
                        "execution_mode": "autonomous_read",
                        "target": {"lead_id": "lesley", "contact": "Lesley Harman", "area": "commercial"},
                    },
                    "evidence": evidence,
                    "executive_result": "Gmail completed the read-only check and returned verified source evidence.",
                    "verified_at": self.NOW.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        stub = StubCommandService()
        service = TonyPersistentAutonomousResultCommandService(
            stub,
            store_path=path,
            clock=lambda: self.NOW,
        )
        return service, stub

    def test_go_ahead_carries_grounded_recommendation_into_controlled_handoff(self):
        service, stub = self._service(
            {
                "summary": "Lesley replied positively and asked what a first conversation would involve.",
                "recommended_next_action": "Reply to Lesley and offer a 30-minute discovery call.",
                "thread_id": "thread-1",
                "read_only": True,
            }
        )

        response = service.execute("OK, do that", [])

        self.assertEqual(response.command, "autonomous_result_action")
        self.assertEqual(response.data["intent"], "progress_verified_autonomous_result")
        self.assertEqual(response.data["grounded_next_action"], "Reply to Lesley and offer a 30-minute discovery call.")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Gmail")
        self.assertTrue(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
        self.assertEqual(handoff["dispatch"]["state"], "awaiting_approval")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("remains behind your approval", response.message)
        self.assertEqual(stub.calls, [])

    def test_safe_internal_recommendation_is_routed_without_inventing_execution(self):
        service, _ = self._service(
            {
                "summary": "The account needs a sharper discovery hypothesis before outreach.",
                "recommended_next_action": "Prepare a one-page discovery hypothesis from the verified evidence.",
                "thread_id": "thread-1",
                "read_only": True,
            }
        )

        response = service.execute("Go ahead", [])

        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Claude")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertEqual(handoff["execution_truth"], "handoff_prepared_only")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("eligible for autonomous execution", response.message)

    def test_action_request_refuses_to_invent_next_move_when_worker_return_has_none(self):
        service, stub = self._service(
            {
                "summary": "The thread was retrieved successfully but contains no decision-grade recommendation.",
                "thread_id": "thread-1",
                "read_only": True,
            }
        )

        response = service.execute("Do it", [])

        self.assertEqual(response.data["execution_status"], "insufficient_grounded_action")
        self.assertNotIn("execution_handoff", response.data)
        self.assertIn("will not invent", response.message)
        self.assertEqual(stub.calls, [])


if __name__ == "__main__":
    unittest.main()
