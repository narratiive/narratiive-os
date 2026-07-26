from __future__ import annotations

import unittest
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from runtime.engineering_orchestrator import (
    EngineeringOrchestrationError,
    EngineeringOrchestrationService,
    EngineeringRunSnapshot,
)


@contextmanager
def unlocked_task(_task_id: str):
    yield


def snapshot(*, state: str = "implementation_running") -> EngineeringRunSnapshot:
    return EngineeringRunSnapshot(
        task_id="eng-81",
        task_digest="task-digest",
        run_id="run-81",
        workspace_id="agency",
        client_id="agency-client",
        repository="narratiive/narratiive-os",
        issue_number=81,
        issue_url="https://github.test/issues/81",
        state=state,
        policy_version="1",
        policy_digest="policy-digest",
        branch="tony/eng-81",
        attempt=1,
        max_attempts=2,
    )


def service_with(current: EngineeringRunSnapshot | None):
    service = EngineeringOrchestrationService.__new__(EngineeringOrchestrationService)
    service._task_lock = unlocked_task
    service._verify_journal = Mock()
    service._context = Mock(
        return_value=(
            SimpleNamespace(task_id="eng-81", digest="task-digest"),
            SimpleNamespace(
                issue_number=81,
                issue_url="https://github.test/issues/81",
            ),
            "approved-artifact",
        )
    )
    service._latest = Mock(return_value=current)
    service._validate_snapshot = Mock()
    service._required = Mock(
        side_effect=lambda value, field: value
        if isinstance(value, str) and value.strip()
        else (_ for _ in ()).throw(
            EngineeringOrchestrationError(f"{field} is required")
        )
    )
    service._transition = Mock(side_effect=lambda _current, next_value, **_kwargs: next_value)
    return service


class EngineeringOrchestrationCancelTests(unittest.TestCase):
    def test_cancel_preserves_evidence_and_records_authorised_transition(self):
        current = snapshot()
        service = service_with(current)

        result = service.cancel(
            "eng-81",
            command_id="cancel-81",
            actor="matt",
        )

        self.assertEqual(result.state, "cancelled")
        self.assertEqual(result.error, "cancelled by authorised command")
        self.assertFalse(result.retryable)
        self.assertEqual(result.run_id, current.run_id)
        self.assertEqual(result.artifact_ids, current.artifact_ids)
        service._transition.assert_called_once()
        _, next_value = service._transition.call_args.args
        self.assertEqual(next_value, replace(current, state="cancelled", error="cancelled by authorised command", retryable=False))
        self.assertEqual(service._transition.call_args.kwargs["actor"], "matt")
        self.assertEqual(service._transition.call_args.kwargs["command_id"], "cancel-81")

    def test_cancel_is_idempotent_after_cancellation(self):
        current = snapshot(state="cancelled")
        service = service_with(current)

        result = service.cancel(
            "eng-81",
            command_id="cancel-again",
            actor="matt",
        )

        self.assertIs(result, current)
        service._transition.assert_not_called()

    def test_cancel_rejects_completed_or_missing_runs(self):
        completed = service_with(snapshot(state="implementation_complete"))
        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "completed engineering implementation cannot be cancelled",
        ):
            completed.cancel(
                "eng-81",
                command_id="cancel-complete",
                actor="matt",
            )
        completed._transition.assert_not_called()

        missing = service_with(None)
        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "engineering task has no implementation run",
        ):
            missing.cancel(
                "eng-81",
                command_id="cancel-missing",
                actor="matt",
            )
        missing._transition.assert_not_called()

    def test_cancel_requires_attributed_actor_and_command(self):
        service = service_with(snapshot())

        with self.assertRaisesRegex(EngineeringOrchestrationError, "actor is required"):
            service.cancel("eng-81", command_id="cancel-81", actor="")
        with self.assertRaisesRegex(EngineeringOrchestrationError, "command_id is required"):
            service.cancel("eng-81", command_id="", actor="matt")
        service._transition.assert_not_called()


if __name__ == "__main__":
    unittest.main()
