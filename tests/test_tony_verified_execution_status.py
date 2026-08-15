from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_verified_execution_status import TonyVerifiedExecutionStatusCommandService


class StubPersistentResultService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, context=None, *, stale=False, response=None):
        self._last_verified_result = context
        self.stale = stale
        self.calls = []
        self.cleared = False
        self.response = response or CommandResponse("delegated", "healthy", "delegated", {})

    def _context_is_stale(self, context):
        return self.stale

    def _clear_context(self):
        self.cleared = True

    def execute(self, command, objects):
        self.calls.append(command)
        return self.response


def verified_gmail_context():
    return {
        "worker": "Gmail",
        "dispatch": {
            "worker": "Gmail",
            "execution_mode": "approval_gated_write",
            "state": "approved_pending_execution",
            "approval_granted": True,
        },
        "evidence": {
            "sent": True,
            "message_id": "gmail-123",
            "summary": "The approved reply was sent to Lesley.",
        },
        "executive_result": "Gmail completed the approved action.",
        "verified_at": "2026-08-15T20:00:00+00:00",
    }


def verified_write_response():
    return CommandResponse(
        "autonomous_result_action",
        "healthy",
        "Approved action completed.",
        {
            "execution_status": "approved_step_verified",
            "executive_result": "Gmail completed the approved message send.",
            "dispatch_result": {
                "worker": "Gmail",
                "status": "verified",
                "evidence": {"sent": True, "message_id": "gmail-456"},
            },
            "execution_handoff": {
                "action": "reply to Lesley and offer a discovery call",
                "dispatch": {
                    "worker": "Gmail",
                    "execution_mode": "approval_gated_write",
                    "target": {"contact": "Lesley"},
                },
            },
        },
    )


def verified_write_outcome(*, result_id="gmail-456", state="positive"):
    return {
        "approved_write_outcome": {
            "execution_result_id": result_id,
            "outcome_status": state,
            "evidence": {"reply_received": True, "meeting_interest": True},
            "summary": "Lesley replied positively and agreed to discuss a discovery call.",
        }
    }


class TonyVerifiedExecutionStatusTests(unittest.TestCase):
    def test_did_that_send_answers_from_verified_write_evidence_without_redispatching(self):
        base = StubPersistentResultService(verified_gmail_context())
        service = TonyVerifiedExecutionStatusCommandService(base)

        response = service.execute("Did that send?", [])

        self.assertEqual(response.command, "verified_execution_status")
        self.assertTrue(response.data["execution_verified"])
        self.assertEqual(response.data["execution_result_id"], "gmail-123")
        self.assertTrue(response.data["external_action_taken"])
        self.assertFalse(response.data["business_outcome_verified"])
        self.assertIn("returned verified evidence", response.message)
        self.assertNotIn("gmail-123", response.message)
        self.assertEqual(base.calls, [])

    def test_did_that_work_separates_execution_from_business_outcome(self):
        base = StubPersistentResultService(verified_gmail_context())
        service = TonyVerifiedExecutionStatusCommandService(base)

        response = service.execute("OK, did that work?", [])

        self.assertEqual(response.command, "verified_execution_outcome")
        self.assertTrue(response.data["execution_verified"])
        self.assertFalse(response.data["business_outcome_verified"])
        self.assertEqual(response.data["outcome_state"], "unverified")
        self.assertIn("does not prove the business outcome worked", response.message)
        self.assertIn("reply, booking, conversion", response.message)
        self.assertEqual(base.calls, [])

    def test_stale_execution_context_is_not_used_as_confirmation(self):
        base = StubPersistentResultService(verified_gmail_context(), stale=True)
        service = TonyVerifiedExecutionStatusCommandService(base)

        response = service.execute("Has that been sent?", [])

        self.assertFalse(response.data["execution_verified"])
        self.assertEqual(response.data["context_state"], "stale")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIsNone(base._last_verified_result)
        self.assertTrue(base.cleared)
        self.assertEqual(base.calls, [])

    def test_non_write_context_delegates_instead_of_inventing_execution(self):
        context = verified_gmail_context()
        context["dispatch"]["execution_mode"] = "autonomous_read"
        base = StubPersistentResultService(context)
        service = TonyVerifiedExecutionStatusCommandService(base)

        response = service.execute("Did that happen?", [])

        self.assertEqual(response.command, "delegated")
        self.assertEqual(base.calls, ["Did that happen?"])

    def test_verified_approved_write_creates_persistent_outcome_watch(self):
        now = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            base = StubPersistentResultService(response=verified_write_response())
            service = TonyVerifiedExecutionStatusCommandService(base, store_path=path, clock=lambda: now)

            response = service.execute("OK, do that", [])

            self.assertEqual(response.data["execution_status"], "approved_step_verified")
            self.assertTrue(path.exists())
            self.assertEqual(service._awaiting_write_outcome["worker"], "Gmail")
            self.assertIn("reply to Lesley", service._awaiting_write_outcome["action"])
            self.assertEqual(service._awaiting_write_outcome["execution_result_id"], "gmail-456")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("awaiting_write_outcome", persisted)
            self.assertIsNone(persisted["last_write_outcome"])

    def test_due_verified_write_outcome_is_surfaced_in_daily_brief(self):
        now = datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            path.write_text(
                '{"worker":"Gmail","action":"reply to Lesley","verified_at":"2026-08-15T20:00:00+00:00"}',
                encoding="utf-8",
            )
            base = StubPersistentResultService(response=CommandResponse("morning", "healthy", "Normal brief", {}))
            service = TonyVerifiedExecutionStatusCommandService(
                base,
                store_path=path,
                clock=lambda: now,
                check_after=timedelta(hours=24),
            )

            response = service.execute("morning", [])

            self.assertEqual(response.status, "attention")
            self.assertIn("Outcome check", response.message)
            self.assertIn("business effect", response.message)
            self.assertEqual(response.data["verified_write_outcome_watch"]["status"], "business_outcome_unverified")

    def test_recent_verified_write_does_not_create_false_urgency(self):
        now = datetime(2026, 8, 15, 22, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            path.write_text(
                '{"worker":"Gmail","action":"reply to Lesley","verified_at":"2026-08-15T20:00:00+00:00"}',
                encoding="utf-8",
            )
            base = StubPersistentResultService(response=CommandResponse("evening", "healthy", "Normal brief", {}))
            service = TonyVerifiedExecutionStatusCommandService(base, store_path=path, clock=lambda: now)

            response = service.execute("evening", [])

            self.assertEqual(response.status, "healthy")
            self.assertEqual(response.message, "Normal brief")
            self.assertNotIn("verified_write_outcome_watch", response.data)

    def test_matching_outcome_evidence_closes_watch_and_persists_result(self):
        now = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            base = StubPersistentResultService(response=verified_write_response())
            service = TonyVerifiedExecutionStatusCommandService(base, store_path=path, clock=lambda: now)
            service.execute("OK, do that", [])

            response = service.execute("write_outcome", [verified_write_outcome()])

            self.assertEqual(response.command, "verified_write_outcome_review")
            self.assertTrue(response.data["accepted"])
            self.assertTrue(response.data["business_outcome_verified"])
            self.assertEqual(response.data["business_outcome_status"], "positive")
            self.assertFalse(response.data["outcome_watch_active"])
            self.assertIsNone(service._awaiting_write_outcome)
            self.assertEqual(service._last_write_outcome["outcome_status"], "positive")

            restored = TonyVerifiedExecutionStatusCommandService(base, store_path=path, clock=lambda: now)
            self.assertIsNone(restored._awaiting_write_outcome)
            self.assertEqual(restored._last_write_outcome["execution_result_id"], "gmail-456")

    def test_mismatched_outcome_evidence_does_not_close_watch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            base = StubPersistentResultService(response=verified_write_response())
            service = TonyVerifiedExecutionStatusCommandService(base, store_path=path)
            service.execute("OK, do that", [])

            response = service.execute(
                "write_outcome",
                [verified_write_outcome(result_id="another-message")],
            )

            self.assertFalse(response.data["accepted"])
            self.assertTrue(response.data["outcome_watch_active"])
            self.assertIsNotNone(service._awaiting_write_outcome)
            self.assertIsNone(service._last_write_outcome)

    def test_recorded_write_outcome_answers_did_that_work_without_redispatching(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            base = StubPersistentResultService(verified_gmail_context(), response=verified_write_response())
            service = TonyVerifiedExecutionStatusCommandService(base, store_path=path)
            service.execute("OK, do that", [])
            service.execute("outcome_evidence", [verified_write_outcome()])
            base.calls.clear()

            response = service.execute("Did that work?", [])

            self.assertTrue(response.data["business_outcome_verified"])
            self.assertEqual(response.data["outcome_state"], "positive")
            self.assertIn("recorded business outcome", response.message)
            self.assertIn("replied positively", response.message)
            self.assertEqual(base.calls, [])

    def test_resolved_write_outcome_no_longer_alerts_in_daily_brief(self):
        now = datetime(2026, 8, 17, 21, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            base = StubPersistentResultService(response=verified_write_response())
            service = TonyVerifiedExecutionStatusCommandService(base, store_path=path, clock=lambda: now)
            service.execute("OK, do that", [])
            service.execute("write_outcome", [verified_write_outcome()])
            base.response = CommandResponse("morning", "healthy", "Normal brief", {})

            response = service.execute("morning", [])

            self.assertEqual(response.status, "healthy")
            self.assertEqual(response.message, "Normal brief")
            self.assertNotIn("verified_write_outcome_watch", response.data)


if __name__ == "__main__":
    unittest.main()
