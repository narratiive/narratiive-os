from __future__ import annotations

import unittest

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response

    def execute(self, command, objects):
        return self.response


def routed_response(*, eligible=True, state="ready_for_autonomous_dispatch", worker="Gmail"):
    return CommandResponse(
        command="agency_focus_action",
        status="healthy",
        message="Handoff prepared.",
        data={
            "execution_status": "ready_for_handoff",
            "execution_handoff": {
                "worker": worker,
                "approval_required": not eligible,
                "execution_truth": "handoff_prepared_only",
                "dispatch": {
                    "eligible": eligible,
                    "state": state,
                    "worker": worker,
                    "instruction": "retrieve the verified thread",
                    "target": {"lead_id": "lesley"},
                    "expected_evidence": "verified read result",
                    "return_to": "Tony",
                    "execution_truth": "not_dispatched",
                },
            },
        },
    )


class TonyAutonomousDispatchTests(unittest.TestCase):
    def test_eligible_dispatch_runs_and_requires_structured_evidence(self):
        calls = []

        def gmail(contract):
            calls.append(contract)
            return {"thread_id": "thread-123", "message_ids": ["m1", "m2"], "read_only": True}

        service = TonyAutonomousDispatchCommandService(
            StubCommandService(routed_response()),
            dispatchers={"Gmail": gmail},
        )
        response = service.execute("do the first one", [])

        self.assertEqual(len(calls), 1)
        self.assertEqual(response.data["autonomous_dispatch_state"], "dispatch_verified")
        self.assertEqual(response.data["execution_status"], "autonomous_step_verified")
        self.assertEqual(response.data["execution_handoff"]["execution_truth"], "verified_dispatch")
        self.assertEqual(response.data["dispatch_result"]["evidence"]["thread_id"], "thread-123")
        self.assertIn("returned verified evidence", response.message)

    def test_approval_gated_handoff_is_never_dispatched(self):
        calls = []
        service = TonyAutonomousDispatchCommandService(
            StubCommandService(routed_response(eligible=False, state="awaiting_approval")),
            dispatchers={"Gmail": lambda contract: calls.append(contract) or {"sent": True}},
        )

        response = service.execute("send it", [])

        self.assertEqual(calls, [])
        self.assertNotIn("autonomous_dispatch_state", response.data)
        self.assertEqual(response.data["execution_handoff"]["dispatch"]["execution_truth"], "not_dispatched")

    def test_missing_dispatcher_preserves_truth_and_reports_blocker(self):
        service = TonyAutonomousDispatchCommandService(StubCommandService(routed_response()), dispatchers={})

        response = service.execute("do the first one", [])

        self.assertEqual(response.data["autonomous_dispatch_state"], "dispatcher_unavailable")
        self.assertEqual(response.data["execution_handoff"]["dispatch"]["execution_truth"], "not_dispatched")
        self.assertNotIn("dispatch_result", response.data)
        self.assertIn("no live dispatcher is configured", response.message)

    def test_empty_or_failed_dispatch_never_claims_completion(self):
        empty_service = TonyAutonomousDispatchCommandService(
            StubCommandService(routed_response(worker="Claude")),
            dispatchers={"Claude": lambda contract: {}},
        )
        empty = empty_service.execute("do the first one", [])
        self.assertEqual(empty.data["autonomous_dispatch_state"], "dispatch_unverified")
        self.assertEqual(empty.data["execution_handoff"]["execution_truth"], "dispatch_attempted_unverified")

        def broken(contract):
            raise RuntimeError("worker unavailable")

        failed_service = TonyAutonomousDispatchCommandService(
            StubCommandService(routed_response(worker="Claude")),
            dispatchers={"Claude": broken},
        )
        failed = failed_service.execute("do the first one", [])
        self.assertEqual(failed.data["autonomous_dispatch_state"], "dispatch_failed")
        self.assertNotIn("dispatch_result", failed.data)
        self.assertIn("did not return verified evidence", failed.message)


if __name__ == "__main__":
    unittest.main()
