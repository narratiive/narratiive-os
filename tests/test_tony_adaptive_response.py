from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_command_service import CommandResponse
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService


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


def strong_return() -> dict:
    return {
        "options": [
            {"name": "A", "approach": "Change the opening proposition."},
            {"name": "B", "approach": "Change the timing and call to action."},
        ],
        "recommendation": "Option A because it directly addresses the weak response signal.",
        "changed_variable": "opening proposition",
        "success_signal": "A qualified reply or discovery booking within three business days.",
    }


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

    def test_approval_after_adaptation_prepares_bounded_worker_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)
            service.execute("What should we try instead?", [])
            response = service.execute("OK, go ahead with the redesign", [])
            self.assertEqual(response.command, "executive_adaptation_handoff")
            self.assertEqual(response.data["adaptation_status"], "worker_handoff_ready")
            self.assertIn("changed_variable", response.data["handoff"]["required_return"])
            self.assertIn("success_signal", response.data["handoff"]["required_return"])
            self.assertFalse(response.data["execution_performed"])

    def test_strong_redesign_return_is_reviewed_before_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)
            service.execute("What should we try instead?", [])
            service.execute("Go ahead with the redesign", [])
            response = service.execute("Review what Claude returned", [strong_return()])
            self.assertEqual(response.data["adaptation_status"], "ready_for_approval")
            self.assertEqual(response.data["review"]["option_count"], 2)
            self.assertTrue(response.data["approval_required"])
            self.assertFalse(response.data["execution_performed"])
            self.assertIn("ready for approval", response.message)

    def test_final_approval_creates_controlled_test_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            action_store = Path(tmp) / "focus.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(
                StubCommandService(),
                learning_store_path=store,
                action_store_path=action_store,
                clock=lambda: datetime(2026, 8, 15, 2, 30, tzinfo=timezone.utc),
            )
            service.execute("What should we try instead?", [])
            service.execute("Go ahead with the redesign", [])
            service.execute("Review what Claude returned", [strong_return()])
            response = service.execute("OK, run the test", [])
            self.assertEqual(response.command, "executive_adaptive_test_handoff")
            self.assertEqual(response.data["adaptation_status"], "approved_test_handoff_ready")
            handoff = response.data["execution_handoff"]
            self.assertEqual(handoff["task_type"], "approved_adaptive_test")
            self.assertEqual(handoff["priority"]["key"], "lead:lesley")
            self.assertEqual(handoff["changed_variable"], "opening proposition")
            self.assertIn("qualified reply", handoff["success_signal"])
            self.assertTrue(handoff["completion_evidence_required"])
            self.assertTrue(handoff["outcome_evidence_required"])
            self.assertTrue(handoff["action_id"].startswith("adaptive:lead:lesley:"))
            self.assertFalse(response.data["execution_performed"])
            self.assertFalse(response.data["external_action_taken"])

    def test_approved_adaptive_test_enters_persistent_action_accountability(self):
        with tempfile.TemporaryDirectory() as tmp:
            learning_store = Path(tmp) / "learning.json"
            action_store = Path(tmp) / "focus.json"
            write_lesson(learning_store, status="negative")
            service = TonyAdaptiveResponseCommandService(
                StubCommandService(),
                learning_store_path=learning_store,
                action_store_path=action_store,
                clock=lambda: datetime(2026, 8, 15, 2, 30, tzinfo=timezone.utc),
            )
            service.execute("What should we try instead?", [])
            service.execute("Go ahead with the redesign", [])
            service.execute("Review what Claude returned", [strong_return()])
            approved = service.execute("Run the test", [])

            restarted = TonyPersistentAgencyFocusCommandService(StubCommandService(), store_path=action_store)
            status = restarted.execute("What's happening with that?", [])

            self.assertEqual(status.command, "agency_focus_action_status")
            self.assertEqual(status.data["execution_status"], "awaiting_worker_confirmation")
            pending = status.data["pending_action"]
            self.assertEqual(pending["action_id"], approved.data["execution_handoff"]["action_id"])
            self.assertTrue(pending["adaptive_test"])
            self.assertEqual(pending["changed_variable"], "opening proposition")
            self.assertIn("qualified reply", pending["success_signal"])
            self.assertFalse(status.data["external_action_taken"])

    def test_final_approval_without_reviewed_redesign_does_not_invent_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)
            response = service.execute("Run the test", [])
            self.assertEqual(response.command, "delegated")

    def test_weak_redesign_return_is_sent_back_for_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)
            service.execute("What should we try instead?", [])
            service.execute("Go ahead with the redesign", [])
            response = service.execute("Review the redesign", [{"options": [{"name": "A"}]}])
            self.assertEqual(response.data["adaptation_status"], "revision_required")
            self.assertIn("changed variable", response.message)
            self.assertFalse(response.data["execution_performed"])
            follow_up = service.execute("Approve it", [])
            self.assertEqual(follow_up.command, "delegated")

    def test_missing_redesign_return_is_not_treated_as_completed_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            write_lesson(store, status="negative")
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=store)
            service.execute("What should we try instead?", [])
            service.execute("Go ahead with the redesign", [])
            response = service.execute("Is the redesign good enough?", [])
            self.assertEqual(response.data["adaptation_status"], "return_missing")
            self.assertFalse(response.data["execution_performed"])

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

    def test_no_verified_learning_refuses_to_invent_an_alternative(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=Path(tmp) / "missing.json")
            response = service.execute("What do you recommend instead?", [])
            self.assertEqual(response.data["adaptation_status"], "insufficient_evidence")
            self.assertFalse(response.data["execution_performed"])

    def test_unrelated_command_delegates_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyAdaptiveResponseCommandService(StubCommandService(), learning_store_path=Path(tmp) / "missing.json")
            response = service.execute("What are today's leads?", [])
            self.assertEqual(response.command, "delegated")


if __name__ == "__main__":
    unittest.main()
