from __future__ import annotations

import json
import tempfile
import unittest
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
        return CommandResponse(
            command="agency_focus_action",
            status="healthy",
            message="Handoff prepared.",
            data={
                "execution_handoff": {
                    "worker": "Gmail",
                    "approval_required": False,
                    "execution_truth": "handoff_prepared_only",
                    "dispatch": {
                        "eligible": True,
                        "state": "ready_for_autonomous_dispatch",
                        "worker": "Gmail",
                        "instruction": "retrieve the verified thread",
                        "target": {"lead_id": "lesley"},
                        "execution_mode": "autonomous_read",
                        "expected_evidence": "verified read result",
                        "return_to": "Tony",
                        "execution_truth": "not_dispatched",
                    },
                },
            },
        )


class TonyPersistentAutonomousResultTests(unittest.TestCase):
    def test_verified_result_survives_service_restart_and_supports_follow_up(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            first_base = StubCommandService()
            first = TonyPersistentAutonomousResultCommandService(
                first_base,
                dispatchers={
                    "Gmail": lambda contract: {
                        "thread_id": "thread-123",
                        "read_only": True,
                        "summary": "Lesley replied positively and asked for availability next week.",
                        "recommended_next_action": "Offer two discovery slots next week.",
                    }
                },
                store_path=path,
            )

            dispatched = first.execute("do the first one", [])
            self.assertEqual(dispatched.data["execution_status"], "autonomous_step_verified")
            self.assertTrue(path.exists())

            restarted_base = StubCommandService()
            restarted = TonyPersistentAutonomousResultCommandService(
                restarted_base,
                dispatchers={},
                store_path=path,
            )
            follow_up = restarted.execute("What came back?", [])

            self.assertEqual(follow_up.command, "autonomous_result_followup")
            self.assertIn("Lesley replied positively", follow_up.message)
            self.assertNotIn("thread-123", follow_up.message)
            self.assertEqual(restarted_base.calls, [])

    def test_recommendation_survives_restart_without_redispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text(
                json.dumps(
                    {
                        "worker": "Gmail",
                        "dispatch": {"worker": "Gmail", "execution_mode": "autonomous_read"},
                        "evidence": {
                            "thread_id": "thread-123",
                            "read_only": True,
                            "summary": "Lesley replied positively.",
                            "recommended_next_action": "Offer two discovery slots next week.",
                        },
                        "executive_result": "Gmail completed the safe step. Lesley replied positively.",
                    }
                ),
                encoding="utf-8",
            )
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(base, dispatchers={}, store_path=path)

            follow_up = service.execute("What do you recommend?", [])

            self.assertEqual(follow_up.command, "autonomous_result_recommendation")
            self.assertEqual(follow_up.data["proposed_next_action"], "Offer two discovery slots next week.")
            self.assertEqual(base.calls, [])

    def test_corrupt_or_incomplete_context_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text('{"worker":"Gmail","evidence":{}}', encoding="utf-8")
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(base, dispatchers={}, store_path=path)

            response = service.execute("What came back?", [])

            self.assertEqual(base.calls, ["What came back?"])
            self.assertEqual(response.command, "agency_focus_action")
            self.assertNotEqual(response.command, "autonomous_result_followup")


if __name__ == "__main__":
    unittest.main()
