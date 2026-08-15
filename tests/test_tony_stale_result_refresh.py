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
        return CommandResponse("delegated", "healthy", "delegated", {})


def stale_read_context() -> dict:
    return {
        "worker": "Gmail",
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
        "evidence": {
            "thread_id": "thread-old",
            "read_only": True,
            "summary": "Old result.",
        },
        "executive_result": "Gmail completed the safe step. Old result.",
        "verified_at": NOW.isoformat(),
    }


class TonyStaleResultRefreshTests(unittest.TestCase):
    def test_stale_read_follow_up_refreshes_verified_evidence_instead_of_using_old_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text(json.dumps(stale_read_context()), encoding="utf-8")
            current = [NOW]
            calls: list[dict] = []

            def gmail(dispatch):
                calls.append(dispatch)
                return {
                    "thread_id": "thread-fresh",
                    "read_only": True,
                    "summary": "Lesley has now replied and asked for two discovery times.",
                    "recommended_next_action": "Offer two discovery slots next week.",
                }

            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(
                base,
                dispatchers={"Gmail": gmail},
                store_path=path,
                clock=lambda: current[0],
            )
            current[0] = NOW + timedelta(hours=9)

            response = service.execute("What came back?", [])

            self.assertEqual(response.command, "autonomous_result_refreshed")
            self.assertTrue(response.data["refresh_verified"])
            self.assertEqual(response.data["context_state"], "fresh")
            self.assertIn("Lesley has now replied", response.message)
            self.assertEqual(base.calls, [])
            self.assertEqual(len(calls), 1)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["evidence"]["thread_id"], "thread-fresh")
            self.assertEqual(stored["verified_at"], current[0].isoformat())

    def test_stale_internal_preparation_is_not_silently_recreated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            value = stale_read_context()
            value["worker"] = "Claude"
            value["dispatch"]["worker"] = "Claude"
            value["dispatch"]["execution_mode"] = "autonomous_prepare"
            path.write_text(json.dumps(value), encoding="utf-8")
            current = [NOW]
            worker_calls: list[dict] = []
            base = StubCommandService()
            service = TonyPersistentAutonomousResultCommandService(
                base,
                dispatchers={"Claude": lambda dispatch: worker_calls.append(dispatch) or {"draft": "new draft"}},
                store_path=path,
                clock=lambda: current[0],
            )
            current[0] = NOW + timedelta(hours=9)

            response = service.execute("What came back?", [])

            self.assertEqual(response.command, "autonomous_result_stale")
            self.assertEqual(response.data["context_state"], "stale")
            self.assertEqual(worker_calls, [])
            self.assertEqual(base.calls, [])

    def test_failed_refresh_remains_unverified_and_does_not_restore_stale_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autonomous-result-context.json"
            path.write_text(json.dumps(stale_read_context()), encoding="utf-8")
            current = [NOW]
            service = TonyPersistentAutonomousResultCommandService(
                StubCommandService(),
                dispatchers={"Gmail": lambda dispatch: {"error": "thread unavailable"}},
                store_path=path,
                clock=lambda: current[0],
            )
            current[0] = NOW + timedelta(hours=9)

            response = service.execute("What do you recommend?", [])

            self.assertEqual(response.command, "autonomous_result_refresh_unverified")
            self.assertFalse(response.data["refresh_verified"])
            self.assertFalse(path.exists())
            self.assertIn("not strong enough", response.message)


if __name__ == "__main__":
    unittest.main()
