from __future__ import annotations

import unittest
from contextlib import contextmanager
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
        task_id="eng-82",
        task_digest="task-digest",
        run_id="run-82",
        workspace_id="agency",
        client_id="agency-client",
        repository="narratiive/narratiive-os",
        issue_number=82,
        issue_url="https://github.test/issues/82",
        state=state,
        policy_version="1",
        policy_digest="policy-digest",
        branch="tony/eng-82",
        attempt=1,
        max_attempts=2,
    )


def service_with(current: EngineeringRunSnapshot | None):
    task = SimpleNamespace(task_id="eng-82", digest="task-digest")
    binding = SimpleNamespace(
        issue_number=82,
        issue_url="https://github.test/issues/82",
    )
    service = EngineeringOrchestrationService.__new__(EngineeringOrchestrationService)
    service._task_lock = unlocked_task
    service._verify_journal = Mock()
    service._context = Mock(return_value=(task, binding, "approved-artifact"))
    service._latest = Mock(return_value=current)
    service._validate_snapshot = Mock()
    service._recover_locked = Mock(return_value=current)
    return service, task, binding


class EngineeringOrchestrationGetTests(unittest.TestCase):
    def test_get_returns_validated_latest_snapshot(self):
        current = snapshot()
        service, task, binding = service_with(current)

        result = service.get("eng-82")

        self.assertIs(result, current)
        service._verify_journal.assert_called_once_with()
        service._context.assert_called_once_with("eng-82")
        service._latest.assert_called_once_with("eng-82")
        service._validate_snapshot.assert_called_once_with(current, task, binding)

    def test_get_rejects_missing_run_without_validation(self):
        service, _task, _binding = service_with(None)

        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "engineering task has no implementation run",
        ):
            service.get("eng-82")

        service._validate_snapshot.assert_not_called()


class EngineeringOrchestrationRecoverTests(unittest.TestCase):
    def test_recover_delegates_to_locked_recovery_with_trusted_context(self):
        current = snapshot(state="failed")
        service, task, binding = service_with(current)

        result = service.recover("eng-82", actor="Tony")

        self.assertIs(result, current)
        service._verify_journal.assert_called_once_with()
        service._context.assert_called_once_with("eng-82")
        service._latest.assert_called_once_with("eng-82")
        service._recover_locked.assert_called_once_with(
            current,
            task,
            binding,
            "approved-artifact",
            actor="Tony",
        )

    def test_recover_rejects_missing_run_before_recovery(self):
        service, _task, _binding = service_with(None)

        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "engineering task has no implementation run",
        ):
            service.recover("eng-82")

        service._recover_locked.assert_not_called()

    def test_recover_preserves_explicit_actor_attribution(self):
        current = snapshot()
        service, task, binding = service_with(current)

        service.recover("eng-82", actor="matt")

        service._recover_locked.assert_called_once_with(
            current,
            task,
            binding,
            "approved-artifact",
            actor="matt",
        )


if __name__ == "__main__":
    unittest.main()
