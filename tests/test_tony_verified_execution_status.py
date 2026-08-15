from __future__ import annotations

import unittest

from runtime.tony_command_service import CommandResponse
from runtime.tony_verified_execution_status import TonyVerifiedExecutionStatusCommandService


class StubPersistentResultService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, context=None, *, stale=False):
        self._last_verified_result = context
        self.stale = stale
        self.calls = []
        self.cleared = False

    def _context_is_stale(self, context):
        return self.stale

    def _clear_context(self):
        self.cleared = True

    def execute(self, command, objects):
        self.calls.append(command)
        return CommandResponse("delegated", "healthy", "delegated", {})


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


if __name__ == "__main__":
    unittest.main()
