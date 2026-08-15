from __future__ import annotations

import unittest

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


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
                "execution_status": "ready_for_handoff",
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


class TonyAutonomousResultFollowupTests(unittest.TestCase):
    def test_follow_up_recalls_verified_result_without_redispatching(self):
        base = StubCommandService()
        dispatch_calls = []
        service = TonyAutonomousDispatchCommandService(
            base,
            dispatchers={
                "Gmail": lambda contract: dispatch_calls.append(contract) or {
                    "thread_id": "thread-123",
                    "read_only": True,
                    "summary": "Lesley replied positively and asked for availability next week.",
                    "recommended_next_action": "Offer two discovery slots next week.",
                }
            },
        )

        first = service.execute("do the first one", [])
        follow_up = service.execute("What came back?", [])

        self.assertEqual(first.data["execution_status"], "autonomous_step_verified")
        self.assertEqual(len(dispatch_calls), 1)
        self.assertEqual(len(base.calls), 1)
        self.assertEqual(follow_up.command, "autonomous_result_followup")
        self.assertIn("Lesley replied positively", follow_up.message)
        self.assertNotIn("thread-123", follow_up.message)
        self.assertFalse(follow_up.data["external_action_taken"])

    def test_follow_up_recommendation_uses_grounded_returned_next_action(self):
        base = StubCommandService()
        service = TonyAutonomousDispatchCommandService(
            base,
            dispatchers={
                "Gmail": lambda contract: {
                    "thread_id": "thread-123",
                    "read_only": True,
                    "summary": "Lesley replied positively.",
                    "recommended_next_action": "Offer two discovery slots next week.",
                }
            },
        )

        service.execute("do the first one", [])
        follow_up = service.execute("OK, what do you recommend?", [])

        self.assertEqual(follow_up.command, "autonomous_result_recommendation")
        self.assertEqual(follow_up.data["proposed_next_action"], "Offer two discovery slots next week.")
        self.assertIn("Offer two discovery slots next week", follow_up.message)
        self.assertIn("approval boundary", follow_up.message)
        self.assertEqual(len(base.calls), 1)

    def test_follow_up_does_not_invent_next_action_when_worker_return_lacks_one(self):
        base = StubCommandService()
        service = TonyAutonomousDispatchCommandService(
            base,
            dispatchers={
                "Gmail": lambda contract: {
                    "thread_id": "thread-123",
                    "read_only": True,
                    "summary": "No reply is present in the verified thread.",
                }
            },
        )

        service.execute("do the first one", [])
        follow_up = service.execute("What next?", [])

        self.assertEqual(follow_up.command, "autonomous_result_recommendation")
        self.assertEqual(follow_up.data["proposed_next_action"], "")
        self.assertIn("not enough grounded next-action evidence", follow_up.message)
        self.assertIn("re-rank", follow_up.message)
        self.assertEqual(len(base.calls), 1)


if __name__ == "__main__":
    unittest.main()
