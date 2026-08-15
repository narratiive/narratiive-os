from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_command_service import CommandResponse


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


def write_lesson(path: Path, *, status: str) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "priority_key": "lead:lesley",
                    "priority_label": "Lesley Harman",
                    "outcome_status": status,
                    "outcome_summary": "The follow-up produced no discovery conversation.",
                    "recorded_at": "2026-08-14T21:00:00+00:00",
                    "guidance": "Use the evidence conservatively.",
                }
            ]
        ),
        encoding="utf-8",
    )


class TonyAdaptiveResponseTests(unittest.TestCase):
    def test_negative_outcome_becomes_worker_ready_redesign_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)

            response = service.execute("What should we try instead?", [])

            self.assertEqual(response.command, "executive_adaptation")
            self.assertEqual(response.data["adaptation_status"], "ready_for_adaptation_design")
            self.assertEqual(response.data["adaptation_brief"]["worker"], "Claude")
            self.assertEqual(response.data["adaptation_brief"]["review_owner"], "Tony")
            self.assertTrue(response.data["adaptation_brief"]["approval_required"])
            self.assertFalse(response.data["execution_performed"])
            self.assertIn("one meaningful variable", response.message)
            self.assertIn("Do not repeat the previous approach unchanged.", response.data["adaptation_brief"]["constraints"])

    def test_approval_after_adaptation_prepares_bounded_worker_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)

            service.execute("What should we try instead?", [])
            response = service.execute("OK, go ahead with the redesign", [])

            self.assertEqual(response.command, "executive_adaptation_handoff")
            self.assertEqual(response.data["adaptation_status"], "worker_handoff_ready")
            self.assertEqual(response.data["handoff"]["worker"], "Claude")
            self.assertEqual(response.data["handoff"]["review_owner"], "Tony")
            self.assertIn("changed_variable", response.data["handoff"]["required_return"])
            self.assertIn("success_signal", response.data["handoff"]["required_return"])
            self.assertFalse(response.data["execution_performed"])
            self.assertIn("Nothing has been executed externally yet", response.message)

    def test_adaptation_approval_without_pending_context_delegates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)

            response = service.execute("Go ahead with the redesign", [])

            self.assertEqual(response.command, "delegated")

    def test_provisional_outcome_cannot_be_approved_into_redesign_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="inconclusive")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)

            first = service.execute("How should we adapt?", [])
            second = service.execute("Go ahead", [])

            self.assertEqual(first.data["adaptation_status"], "gather_evidence_before_adaptation")
            self.assertEqual(second.command, "delegated")

    def test_inconclusive_outcome_does_not_trigger_premature_redesign(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="inconclusive")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)

            response = service.execute("How should we adapt?", [])

            self.assertEqual(response.data["adaptation_status"], "gather_evidence_before_adaptation")
            self.assertNotIn("adaptation_brief", response.data)
            self.assertFalse(response.data["execution_performed"])
            self.assertIn("too weak a signal", response.message)

    def test_no_verified_learning_refuses_to_invent_an_alternative(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyAdaptiveResponseCommandService(
                StubCommandService(), learning_store_path=Path(tmp) / "missing.json"
            )

            response = service.execute("What do you recommend instead?", [])

            self.assertEqual(response.data["adaptation_status"], "insufficient_evidence")
            self.assertFalse(response.data["execution_performed"])

    def test_unrelated_command_delegates_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyAdaptiveResponseCommandService(
                StubCommandService(), learning_store_path=Path(tmp) / "missing.json"
            )

            response = service.execute("What are today's leads?", [])

            self.assertEqual(response.command, "delegated")


if __name__ == "__main__":
    unittest.main()
