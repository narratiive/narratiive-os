import unittest
from datetime import date
from decimal import Decimal

from runtime.commercial_intelligence import CommercialIntelligenceEngine, CommercialOpportunity


class CommercialIntelligenceTests(unittest.TestCase):
    def test_calculates_pipeline_and_weighted_value(self) -> None:
        snapshot = CommercialIntelligenceEngine().evaluate(
            [
                CommercialOpportunity("a", "Alpha", "qualified", Decimal("10000"), date(2026, 7, 31)),
                CommercialOpportunity("b", "Beta", "proposal", Decimal("20000"), date(2026, 7, 31)),
                CommercialOpportunity("c", "Won", "won", Decimal("5000"), date(2026, 7, 31)),
            ],
            as_of=date(2026, 8, 2),
        )
        self.assertEqual(snapshot.pipeline_value, Decimal("30000.00"))
        self.assertEqual(snapshot.weighted_pipeline_value, Decimal("14000.00"))
        self.assertEqual(snapshot.open_opportunities, 2)

    def test_stalled_opportunities_become_actions_in_priority_order(self) -> None:
        snapshot = CommercialIntelligenceEngine().evaluate(
            [
                CommercialOpportunity("a", "Alpha", "qualified", Decimal("10000"), date(2026, 7, 20)),
                CommercialOpportunity("b", "Beta", "proposal", Decimal("20000"), date(2026, 7, 25), next_action="Call Beta"),
                CommercialOpportunity("c", "Current", "proposal", Decimal("50000"), date(2026, 8, 1)),
            ],
            as_of=date(2026, 8, 2),
            stalled_after_days=7,
        )
        self.assertEqual([item.opportunity_id for item in snapshot.stalled_opportunities], ["a", "b"])
        self.assertEqual(snapshot.actions_required, ("Re-engage Alpha", "Call Beta"))

    def test_closed_opportunities_are_not_stalled(self) -> None:
        snapshot = CommercialIntelligenceEngine().evaluate(
            [CommercialOpportunity("a", "Alpha", "lost", Decimal("10000"), date(2026, 1, 1))],
            as_of=date(2026, 8, 2),
        )
        self.assertEqual(snapshot.stalled_opportunities, ())
        self.assertEqual(snapshot.pipeline_value, Decimal("0.00"))

    def test_invalid_and_duplicate_data_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative"):
            CommercialOpportunity("a", "Alpha", "lead", Decimal("-1"), date(2026, 8, 2))
        duplicate = CommercialOpportunity("a", "Alpha", "lead", Decimal("1"), date(2026, 8, 2))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            CommercialIntelligenceEngine().evaluate([duplicate, duplicate], as_of=date(2026, 8, 2))


if __name__ == "__main__":
    unittest.main()
