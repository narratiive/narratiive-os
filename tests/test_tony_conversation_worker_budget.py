from __future__ import annotations

import unittest
from unittest import mock

from scripts.run_tony_conversation_worker import budgeted_conversation_executor


class TonyConversationWorkerBudgetTests(unittest.TestCase):
    def test_durable_openclaw_execution_holds_budget_reservation(self) -> None:
        guard = mock.Mock()
        reservation = object()
        guard.reserve_capacity.return_value = reservation
        executor = mock.Mock(return_value="done")

        result = budgeted_conversation_executor(executor, guard, ttl_seconds=120)("research this", "work-1")

        self.assertEqual(result, "done")
        guard.reserve_capacity.assert_called_once_with(ttl_seconds=120)
        executor.assert_called_once_with("research this", "work-1")
        guard.release_reservation.assert_called_once_with(reservation)

    def test_durable_openclaw_execution_retains_reservation_on_ambiguous_failure(self) -> None:
        guard = mock.Mock()
        reservation = object()
        guard.reserve_capacity.return_value = reservation
        executor = mock.Mock(side_effect=RuntimeError("failed"))

        with self.assertRaisesRegex(RuntimeError, "failed"):
            budgeted_conversation_executor(executor, guard, ttl_seconds=120)("research this", "work-1")

        guard.release_reservation.assert_not_called()
        guard.retain_ambiguous_reservation.assert_called_once_with(reservation)


if __name__ == "__main__":
    unittest.main()
