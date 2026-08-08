import unittest
from decimal import Decimal

from runtime.executive_priority_ranking import ExecutivePriorityCandidate, ExecutivePriorityRanker


class ExecutivePriorityRankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ranker = ExecutivePriorityRanker()

    def test_commercial_work_can_outrank_operational_noise(self) -> None:
        priorities = self.ranker.rank(
            [
                ExecutivePriorityCandidate(
                    candidate_id="ops-1",
                    title="Review repository housekeeping",
                    kind="operational",
                    urgency=2,
                    strategic_value=1,
                ),
                ExecutivePriorityCandidate(
                    candidate_id="commercial-1",
                    title="Follow up stalled proposal",
                    kind="commercial",
                    urgency=4,
                    strategic_value=4,
                    commercial_value=Decimal("12000"),
                ),
            ]
        )
        self.assertEqual(priorities[0].candidate_id, "commercial-1")
        self.assertIn("commercial impact", priorities[0].reason)

    def test_limit_produces_short_executive_agenda(self) -> None:
        candidates = [
            ExecutivePriorityCandidate(
                candidate_id=f"item-{index}",
                title=f"Priority {index}",
                kind="operational",
                urgency=index,
                strategic_value=index,
            )
            for index in range(1, 5)
        ]
        priorities = self.ranker.rank(candidates, limit=2)
        self.assertEqual(len(priorities), 2)
        self.assertEqual([item.rank for item in priorities], [1, 2])

    def test_blocked_work_receives_escalation_weight(self) -> None:
        priorities = self.ranker.rank(
            [
                ExecutivePriorityCandidate("a", "Unblocked", "operational", 3, 3),
                ExecutivePriorityCandidate("b", "Blocked", "operational", 3, 3, blocked=True),
            ]
        )
        self.assertEqual(priorities[0].candidate_id, "b")
        self.assertIn("currently blocked", priorities[0].reason)

    def test_duplicate_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.ranker.rank(
                [
                    ExecutivePriorityCandidate("same", "First", "operational", 1, 1),
                    ExecutivePriorityCandidate("same", "Second", "commercial", 1, 1),
                ]
            )

    def test_invalid_limit_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            self.ranker.rank([], limit=0)


if __name__ == "__main__":
    unittest.main()
