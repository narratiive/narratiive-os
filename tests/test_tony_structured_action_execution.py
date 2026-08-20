from __future__ import annotations

import unittest

from runtime.tony_structured_action_execution import (
    StructuredActionExecutionError,
    TonyStructuredActionExecutor,
)


class TonyStructuredActionExecutionTests(unittest.TestCase):
    def test_gmail_write_dispatches_only_with_single_use_approval_and_verified_id(self):
        seen = []

        def gmail(dispatch):
            seen.append(dispatch)
            return {"ok": True, "message_id": "msg-123", "thread_id": "thread-1"}

        executor = TonyStructuredActionExecutor({"Gmail": gmail})
        result = executor.execute(
            {
                "action": "Send the reviewed reply to Jimmy exactly as approved.",
                "surface": "gmail",
                "kind": "write",
                "target": {"contact": "Jimmy"},
                "approval": "openclaw_allow_once",
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_truth"], "verified_executed")
        self.assertEqual(seen[0]["execution_mode"], "approved_write")
        self.assertEqual(seen[0]["approval"], "openclaw_allow_once")
        self.assertEqual(seen[0]["source"], "openclaw_native_tool")

    def test_missing_dispatcher_fails_closed_without_claiming_execution(self):
        result = TonyStructuredActionExecutor({}).execute(
            {
                "action": "Send the email",
                "surface": "gmail",
                "kind": "write",
                "target": {},
                "approval": "openclaw_allow_once",
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "dispatcher_unavailable")
        self.assertEqual(result["execution_truth"], "not_dispatched")

    def test_returned_worker_text_without_decision_grade_identifier_is_not_execution_proof(self):
        executor = TonyStructuredActionExecutor({"Gmail": lambda _dispatch: {"ok": True, "summary": "sent"}})
        result = executor.execute(
            {
                "action": "Send the email",
                "surface": "gmail",
                "kind": "write",
                "target": {},
                "approval": "openclaw_allow_once",
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unverified_execution")
        self.assertEqual(result["execution_truth"], "not_verified")

    def test_explicit_worker_failure_overrides_returned_identifier(self):
        executor = TonyStructuredActionExecutor({"Google Calendar": lambda _dispatch: {"ok": False, "event_id": "evt-1"}})
        result = executor.execute(
            {
                "action": "Book Thursday at 10am",
                "surface": "calendar",
                "kind": "write",
                "target": {"time": "Thursday 10am"},
                "approval": "openclaw_allow_once",
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["execution_truth"], "not_verified")

    def test_write_requires_native_single_use_approval(self):
        executor = TonyStructuredActionExecutor({})
        with self.assertRaises(StructuredActionExecutionError):
            executor.execute({"action": "Send it", "surface": "gmail", "kind": "write", "approval": "yes"})

    def test_reads_and_preparation_cannot_enter_consequential_executor(self):
        executor = TonyStructuredActionExecutor({})
        for kind in ("read", "prepare"):
            with self.subTest(kind=kind), self.assertRaises(StructuredActionExecutionError):
                executor.execute(
                    {
                        "action": "Check or prepare something",
                        "surface": "gmail",
                        "kind": kind,
                        "approval": "openclaw_allow_once",
                    }
                )

    def test_specialist_surfaces_cannot_bypass_openclaw_orchestration_via_write_executor(self):
        executor = TonyStructuredActionExecutor({})
        with self.assertRaises(StructuredActionExecutionError):
            executor.execute(
                {
                    "action": "Have Research Agent change the client record",
                    "surface": "research",
                    "kind": "write",
                    "approval": "openclaw_allow_once",
                }
            )


if __name__ == "__main__":
    unittest.main()
