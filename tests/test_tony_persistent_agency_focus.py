from __future__ import annotations

import tempfile
import unittest
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

    def test_new_empty_focus_clears_stale_persisted_context(self):
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

            empty = TonyPersistentAgencyFocusCommandService(EmptyStub(), store_path=store)
            empty.execute("What matters most?", [])

            restarted = TonyPersistentAgencyFocusCommandService(EmptyStub(), store_path=store)
            response = restarted.execute("Why is that first?", [])
            self.assertEqual(response.command, "delegated")


if __name__ == "__main__":
    unittest.main()
