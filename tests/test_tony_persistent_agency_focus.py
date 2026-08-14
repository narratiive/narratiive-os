from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, command, objects):
        self.calls.append(command)
        if command == "morning":
            return CommandResponse(
                "morning",
                "attention",
                "brief",
                {
                    "agency_state": {"executive_items": []},
                    "commercial_watch": {
                        "positive_replies": [
                            {
                                "lead_id": "lesley-1",
                                "contact": "Lesley Harman",
                                "company": "Harman Communications",
                                "recommended_next_action": "Move the opportunity to discovery.",
                            }
                        ],
                        "overdue": [],
                    },
                },
            )
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyPersistentAgencyFocusTests(unittest.TestCase):
    def test_ranked_focus_survives_service_restart_for_rationale_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            first_inner = StubCommandService()
            first = TonyPersistentAgencyFocusCommandService(first_inner, store_path=store)

            focus = first.execute("What should I focus on today?", [])
            self.assertEqual(focus.data["priorities"][0]["reason"], "new_positive_commercial_intent")
            self.assertTrue(store.exists())

            restarted_inner = StubCommandService()
            restarted = TonyPersistentAgencyFocusCommandService(restarted_inner, store_path=store)
            response = restarted.execute("Why is that first?", [])

            self.assertEqual(response.command, "agency_focus_rationale")
            self.assertIn("positive buying intent", response.message)
            self.assertEqual(restarted_inner.calls, [])

    def test_ranked_focus_survives_service_restart_for_action_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            first = TonyPersistentAgencyFocusCommandService(StubCommandService(), store_path=store)
            first.execute("What matters most?", [])

            restarted = TonyPersistentAgencyFocusCommandService(StubCommandService(), store_path=store)
            response = restarted.execute("OK, do the first one", [])

            self.assertEqual(response.command, "agency_focus_action")
            self.assertEqual(response.data["execution_handoff"]["worker"], "Gmail")
            self.assertEqual(response.data["priority"]["target"]["lead_id"], "lesley-1")
            self.assertFalse(response.data["external_action_taken"])

    def test_prepared_action_survives_restart_and_reports_truthful_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            first = TonyPersistentAgencyFocusCommandService(StubCommandService(), store_path=store)
            first.execute("What matters most?", [])
            first.execute("OK, do the first one", [])

            restarted_inner = StubCommandService()
            restarted = TonyPersistentAgencyFocusCommandService(restarted_inner, store_path=store)
            response = restarted.execute("What's happening with that?", [])

            self.assertEqual(response.command, "agency_focus_action_status")
            self.assertEqual(response.data["execution_status"], "awaiting_worker_confirmation")
            self.assertEqual(response.data["pending_action"]["execution_handoff"]["worker"], "Gmail")
            self.assertFalse(response.data["external_action_taken"])
            self.assertIn("do not yet have confirmation", response.message)
            self.assertEqual(restarted_inner.calls, [])

    def test_repeated_action_request_does_not_create_false_duplicate_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            service = TonyPersistentAgencyFocusCommandService(StubCommandService(), store_path=store)
            service.execute("What matters most?", [])
            service.execute("OK, do the first one", [])
            repeated = service.execute("Do the first one", [])

            self.assertEqual(repeated.command, "agency_focus_action_status")
            self.assertTrue(repeated.data["duplicate_handoff_suppressed"])
            self.assertFalse(repeated.data["external_action_taken"])
            self.assertIn("already prepared", repeated.message)

    def test_stalled_worker_action_is_promoted_into_agency_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
            service = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start,
            )
            service.execute("What matters most?", [])
            service.execute("Do the first one", [])

            later = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start + timedelta(hours=3),
            )
            response = later.execute("What should I focus on today?", [])

            reasons = [item["reason"] for item in response.data["priorities"]]
            self.assertIn("stalled_delegated_action", reasons)
            stalled = next(item for item in response.data["priorities"] if item["reason"] == "stalled_delegated_action")
            self.assertIn("no execution or return evidence", stalled["action"])
            self.assertFalse(response.data["stalled_executive_action"]["requires_matt"])

    def test_stalled_worker_action_is_surfaced_in_daily_brief_without_prompting_for_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
            service = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start,
            )
            service.execute("What matters most?", [])
            service.execute("Do the first one", [])

            later = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start + timedelta(hours=3),
            )
            response = later.execute("morning", [])

            self.assertEqual(response.command, "morning")
            self.assertEqual(response.status, "attention")
            self.assertIn("Stalled action:", response.message)
            self.assertIn("stalled_executive_action", response.data)

    def test_recent_prepared_action_is_not_falsely_called_stalled(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
            service = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start,
            )
            service.execute("What matters most?", [])
            service.execute("Do the first one", [])

            later = TonyPersistentAgencyFocusCommandService(
                StubCommandService(),
                store_path=store,
                clock=lambda: start + timedelta(minutes=90),
            )
            response = later.execute("morning", [])

            self.assertNotIn("Stalled action:", response.message)
            self.assertNotIn("stalled_executive_action", response.data)

    def test_new_empty_focus_clears_stale_priorities_but_keeps_open_action_accountability(self):
        class EmptyStub(StubCommandService):
            def execute(self, command, objects):
                self.calls.append(command)
                if command == "morning":
                    return CommandResponse(
                        "morning",
                        "healthy",
                        "brief",
                        {"agency_state": {"executive_items": []}, "commercial_watch": {}},
                    )
                return CommandResponse("delegated", "healthy", "delegated", {})

        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "focus.json"
            seeded = TonyPersistentAgencyFocusCommandService(StubCommandService(), store_path=store)
            seeded.execute("What matters most?", [])
            seeded.execute("Do the first one", [])

            empty = TonyPersistentAgencyFocusCommandService(EmptyStub(), store_path=store)
            empty.execute("What matters most?", [])

            restarted = TonyPersistentAgencyFocusCommandService(EmptyStub(), store_path=store)
            rationale = restarted.execute("Why is that first?", [])
            status = restarted.execute("What are you waiting on?", [])

            self.assertEqual(rationale.command, "delegated")
            self.assertEqual(status.command, "agency_focus_action_status")
            self.assertFalse(status.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
