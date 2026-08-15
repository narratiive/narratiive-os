from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_autonomous_result import TonyPersistentAutonomousResultCommandService


NOW = datetime(2026, 8, 15, 16, 0, tzinfo=timezone.utc)


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


def context(*, verified_at: datetime) -> dict:
    return {
        "worker": "Gmail",
        "dispatch": {"worker": "Gmail", "execution_mode": "autonomous_read"},
        "evidence": {
            "thread_id": "thread-123",
            "read_only": True,
            "summary": "Lesley replied positively.",
            "recommended_next_action": "Offer two discovery slots next week.",
        },
        "executive_result": "Gmail completed the safe step. Lesley replied positively.",
        "verified_at": verified_at.isoformat(),
    }


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
                clock=lambda: NOW,
            )

            dispatched = first.execute("do the first one", [])
            self.assertEqual(dispatched.data["execution_status"], "autonomous_step_verified")
            self.assertTrue(path.exists())
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["verified_at"], NOW.isoformat())

            restarted_base = StubCommandService()
            restarted = TonyPersistentAutonomousResultCommandService(
                restarted_base,
                dispatchers={},
                store_path=path,
                clock=lambda: NOW + timedelta(hours=1),
            )
            follow_up = restarted.execute("What came back?", [])

            self.assertEqual(follow_up.command, "autonomous_result_followup")
            self.assertIn("Lesley replied positively", follow_up.message)
            self.assertNotIn("thread-123", follow_up.message)
            self.assertEqual(restarted_base.calls, [])

    def test_recommendation_survives_restart_without_redispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text(json.dumps(context(verified_at=NOW - timedelta(hours=2))), encoding="utf-8")
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(
                base,
                dispatchers={},
                store_path=path,
                clock=lambda: NOW,
            )

            follow_up = service.execute("What do you recommend?", [])

            self.assertEqual(follow_up.command, "autonomous_result_recommendation")
            self.assertEqual(follow_up.data["proposed_next_action"], "Offer two discovery slots next week.")
            self.assertEqual(base.calls, [])

    def test_stale_context_is_not_used_for_follow_up_and_is_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text(json.dumps(context(verified_at=NOW - timedelta(hours=9))), encoding="utf-8")
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(
                base,
                dispatchers={},
                store_path=path,
                clock=lambda: NOW,
            )

            response = service.execute("What do you recommend?", [])

            self.assertEqual(response.command, "agency_focus_action")
            self.assertEqual(base.calls, ["What do you recommend?"])
            self.assertFalse(path.exists())

    def test_context_that_becomes_stale_during_runtime_gets_explicit_refresh_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            current = [NOW]
            path.write_text(json.dumps(context(verified_at=NOW)), encoding="utf-8")
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(
                base,
                dispatchers={},
                store_path=path,
                clock=lambda: current[0],
            )
            current[0] = NOW + timedelta(hours=9)

            response = service.execute("What came back?", [])

            self.assertEqual(response.command, "autonomous_result_stale")
            self.assertEqual(response.data["context_state"], "stale")
            self.assertIn("too old", response.message)
            self.assertEqual(base.calls, [])
            self.assertFalse(path.exists())

    def test_newer_verified_result_supersedes_older_persisted_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text(json.dumps(context(verified_at=NOW - timedelta(hours=2))), encoding="utf-8")
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(
                base,
                dispatchers={
                    "Gmail": lambda contract: {
                        "thread_id": "thread-456",
                        "read_only": True,
                        "summary": "A newer verified reply changed the commercial picture.",
                    }
                },
                store_path=path,
                clock=lambda: NOW,
            )

            service.execute("do the first one", [])
            follow_up = service.execute("What came back?", [])

            self.assertIn("newer verified reply", follow_up.message)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["verified_at"], NOW.isoformat())
            self.assertEqual(stored["evidence"]["thread_id"], "thread-456")

    def test_corrupt_incomplete_or_untimestamped_context_is_not_trusted(self):
        cases = [
            '{"worker":"Gmail","evidence":{}}',
            json.dumps(
                {
                    "worker": "Gmail",
                    "dispatch": {"worker": "Gmail"},
                    "evidence": {"thread_id": "thread-123"},
                    "executive_result": "old unversioned result",
                }
            ),
            json.dumps({**context(verified_at=NOW), "verified_at": "not-a-date"}),
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "autonomous-result-context.json"
                    path.write_text(payload, encoding="utf-8")
                    base = StubCommandService()
                    service = TonyPersistentAutonomousResultCommandService(
                        base,
                        dispatchers={},
                        store_path=path,
                        clock=lambda: NOW,
                    )

                    response = service.execute("What came back?", [])

                    self.assertEqual(base.calls, ["What came back?"])
                    self.assertEqual(response.command, "agency_focus_action")
                    self.assertNotEqual(response.command, "autonomous_result_followup")


if __name__ == "__main__":
    unittest.main()
