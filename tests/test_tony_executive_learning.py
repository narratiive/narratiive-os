from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_learning import TonyExecutiveLearningCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self) -> None:
        self.outcome_status = "negative"

    def execute(self, command, objects):
        if command == "outcome_result":
            return CommandResponse(
                "executive_outcome_review",
                "attention",
                "Outcome review recorded.",
                {
                    "accepted": True,
                    "outcome": {
                        "action_id": "a-1",
                        "outcome_status": self.outcome_status,
                        "summary": "The follow-up produced no discovery conversation.",
                        "recorded_at": "2026-08-14T21:00:00+00:00",
                        "priority": {"key": "lead:lesley", "label": "Lesley Harman"},
                    },
                },
            )
        if command == "do_first":
            return CommandResponse(
                "agency_focus_action",
                "healthy",
                "I have prepared the handoff.",
                {
                    "priority": {"key": "lead:lesley", "label": "Lesley Harman"},
                    "execution_status": "ready_for_handoff",
                    "external_action_taken": False,
                },
            )
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyExecutiveLearningTests(unittest.TestCase):
    def test_negative_outcome_blocks_repeating_same_move_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            service = TonyExecutiveLearningCommandService(StubCommandService(), store_path=store)
            service.execute("outcome_result", [])

            response = service.execute("do_first", [])

            self.assertEqual(response.status, "attention")
            self.assertEqual(response.data["execution_status"], "requires_adaptation")
            self.assertEqual(response.data["learning_guard"]["status"], "adapt_before_repeat")
            self.assertIn("adapt the approach", response.message)
            self.assertFalse(response.data["external_action_taken"])

    def test_learning_persists_across_restart_and_can_be_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            first = TonyExecutiveLearningCommandService(StubCommandService(), store_path=store)
            first.execute("outcome_result", [])

            restarted = TonyExecutiveLearningCommandService(StubCommandService(), store_path=store)
            response = restarted.execute("What did we learn?", [])

            self.assertEqual(response.command, "executive_learning")
            self.assertEqual(len(response.data["lessons"]), 1)
            self.assertIn("Lesley Harman", response.message)
            self.assertIn("Do not repeat the same approach unchanged", response.message)

    def test_positive_outcome_informs_repeat_without_blocking_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_stub = StubCommandService()
            service_stub.outcome_status = "positive"
            service = TonyExecutiveLearningCommandService(service_stub, store_path=Path(tmp) / "learning.json")
            service.execute("outcome_result", [])

            response = service.execute("do_first", [])

            self.assertEqual(response.status, "healthy")
            self.assertEqual(response.data["execution_status"], "ready_for_handoff")
            self.assertEqual(response.data["learning_guard"]["status"], "evidence_supported_repeat")
            self.assertEqual(response.data["learning_guard"]["prior_outcome"], "positive")
            self.assertEqual(response.data["learning_guard"]["positive_evidence_count"], 1)
            self.assertIn("last verified outcome", response.message)
            self.assertIn("preserve the elements", response.message.lower())
            self.assertFalse(response.data["external_action_taken"])

    def test_repeated_positive_outcomes_raise_confidence_without_premature_scaling(self):
        with tempfile.TemporaryDirectory() as tmp:
            service_stub = StubCommandService()
            service_stub.outcome_status = "positive"
            service = TonyExecutiveLearningCommandService(service_stub, store_path=Path(tmp) / "learning.json")
            service.execute("outcome_result", [])
            service.execute("outcome_result", [])

            response = service.execute("do_first", [])

            self.assertEqual(response.status, "healthy")
            self.assertEqual(response.data["execution_status"], "ready_for_handoff")
            self.assertEqual(response.data["learning_guard"]["status"], "positive_pattern_emerging")
            self.assertEqual(response.data["learning_guard"]["positive_evidence_count"], 2)
            self.assertIn("emerging pattern", response.message.lower())
            self.assertIn("controlled repeat", response.message.lower())
            self.assertIn("before materially scaling", response.message.lower())
            self.assertFalse(response.data["external_action_taken"])

    def test_learning_is_scoped_to_matching_priority(self):
        class OtherPriorityStub(StubCommandService):
            def execute(self, command, objects):
                response = super().execute(command, objects)
                if command == "do_first":
                    data = dict(response.data)
                    data["priority"] = {"key": "lead:jimmy", "label": "Jimmy Diamond"}
                    return CommandResponse(response.command, response.status, response.message, data)
                return response

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyExecutiveLearningCommandService(OtherPriorityStub(), store_path=Path(tmp) / "learning.json")
            service.execute("outcome_result", [])

            response = service.execute("do_first", [])

            self.assertEqual(response.data["execution_status"], "ready_for_handoff")
            self.assertNotIn("learning_guard", response.data)


if __name__ == "__main__":
    unittest.main()
