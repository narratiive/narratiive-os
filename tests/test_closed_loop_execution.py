import unittest

from runtime.closed_loop_execution import ClosedLoopExecution
from runtime.delegation_framework import DelegatedAssignment


class ClosedLoopExecutionTests(unittest.TestCase):
    def _assignment(self, task_id="task-1", priority=80):
        return DelegatedAssignment(
            task_id=task_id,
            agent_id="commercial-agent",
            agent_name="Commercial Agent",
            capability="commercial",
            priority_score=priority,
        )

    def test_register_start_and_complete_requires_evidence(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment())
        loop.start("task-1")
        completed = loop.complete("task-1", evidence=("proposal:123",))
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.evidence, ("proposal:123",))

    def test_completion_without_evidence_fails_closed(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment())
        loop.start("task-1")
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            loop.complete("task-1", evidence=())

    def test_blocked_work_retries_with_incremented_attempt(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment(), max_attempts=2)
        loop.start("task-1")
        loop.block("task-1", blocker="waiting for client input")
        retried = loop.retry("task-1")
        self.assertEqual(retried.status, "assigned")
        self.assertEqual(retried.attempt, 2)
        self.assertIsNone(retried.blocker)

    def test_exhausted_retry_escalates(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment(), max_attempts=1)
        loop.start("task-1")
        loop.fail("task-1", blocker="provider unavailable")
        escalated = loop.retry("task-1")
        self.assertEqual(escalated.status, "escalated")
        self.assertEqual(escalated.blocker, "provider unavailable")
        self.assertEqual(loop.escalations(), (escalated,))

    def test_unresolved_is_priority_ordered(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment("low", 20))
        loop.register(self._assignment("high", 95))
        self.assertEqual(
            [record.task_id for record in loop.unresolved()],
            ["high", "low"],
        )

    def test_duplicate_registration_fails_closed(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment())
        with self.assertRaisesRegex(ValueError, "duplicate task_id"):
            loop.register(self._assignment())

    def test_invalid_transition_fails_closed(self):
        loop = ClosedLoopExecution()
        loop.register(self._assignment())
        with self.assertRaisesRegex(ValueError, "only in-progress work"):
            loop.complete("task-1", evidence=("evidence",))


if __name__ == "__main__":
    unittest.main()
