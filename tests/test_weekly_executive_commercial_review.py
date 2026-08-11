import unittest
from datetime import date
from decimal import Decimal

from runtime.client_intelligence import (
    ClientIntelligenceEngine,
    ClientRecord,
)
from runtime.closed_loop_execution import ExecutionRecord
from runtime.commercial_intelligence import (
    CommercialIntelligenceEngine,
    CommercialOpportunity,
)
from runtime.weekly_executive_commercial_review import (
    WeeklyExecutiveCommercialReviewBuilder,
)


class WeeklyExecutiveCommercialReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.as_of = date(2026, 8, 11)
        self.builder = WeeklyExecutiveCommercialReviewBuilder()

    def test_combines_commercial_client_and_execution_state(self) -> None:
        commercial = CommercialIntelligenceEngine().evaluate(
            (
                CommercialOpportunity(
                    opportunity_id="opp-1",
                    account_name="Mother Root",
                    stage="proposal",
                    value=Decimal("10000"),
                    last_activity_on=date(2026, 7, 31),
                    next_action="Follow up Mother Root",
                ),
            ),
            as_of=self.as_of,
        )
        clients = ClientIntelligenceEngine().evaluate_portfolio(
            (
                ClientRecord(
                    client_id="client-1",
                    name="Priority Client",
                    last_contact_on=date(2026, 7, 1),
                    revenue_value=Decimal("5000"),
                ),
            ),
            as_of=self.as_of,
        )
        execution = (
            ExecutionRecord(
                task_id="done-1",
                agent_id="commercial-agent",
                capability="commercial",
                priority_score=90,
                status="completed",
                evidence=("proposal:123",),
            ),
            ExecutionRecord(
                task_id="blocked-1",
                agent_id="research-agent",
                capability="research",
                priority_score=80,
                status="escalated",
                blocker="client input missing",
            ),
        )

        review = self.builder.build(commercial, clients, execution)

        self.assertEqual(review.open_opportunities, 1)
        self.assertEqual(review.at_risk_clients, 1)
        self.assertEqual(review.completed_work, 1)
        self.assertEqual(review.escalated_work, 1)
        self.assertTrue(any("Mother Root" in item for item in review.risks))
        self.assertTrue(any("Priority Client" in item for item in review.risks))
        self.assertTrue(any("blocked-1" in item for item in review.risks))
        self.assertIn("Follow up Mother Root", review.priorities)

    def test_empty_business_state_creates_growth_priority(self) -> None:
        commercial = CommercialIntelligenceEngine().evaluate((), as_of=self.as_of)
        clients = ClientIntelligenceEngine().evaluate_portfolio((), as_of=self.as_of)

        review = self.builder.build(commercial, clients, ())

        self.assertEqual(review.priorities, ("Create new qualified commercial opportunities",))
        self.assertEqual(review.risks, ())

    def test_render_is_bounded_and_business_facing(self) -> None:
        commercial = CommercialIntelligenceEngine().evaluate((), as_of=self.as_of)
        clients = ClientIntelligenceEngine().evaluate_portfolio((), as_of=self.as_of)
        review = self.builder.build(commercial, clients, ())

        rendered = review.render(max_items_per_section=2)

        self.assertIn("Weekly executive review", rendered)
        self.assertIn("Commercial:", rendered)
        self.assertIn("Clients:", rendered)
        self.assertIn("Execution:", rendered)
        self.assertIn("Next week:", rendered)
        self.assertNotIn("repository", rendered.lower())

    def test_duplicate_execution_ids_fail_closed(self) -> None:
        commercial = CommercialIntelligenceEngine().evaluate((), as_of=self.as_of)
        clients = ClientIntelligenceEngine().evaluate_portfolio((), as_of=self.as_of)
        record = ExecutionRecord(
            task_id="same",
            agent_id="agent",
            capability="operations",
            priority_score=20,
        )

        with self.assertRaisesRegex(ValueError, "duplicate execution task_id"):
            self.builder.build(commercial, clients, (record, record))

    def test_invalid_render_limit_fails_closed(self) -> None:
        commercial = CommercialIntelligenceEngine().evaluate((), as_of=self.as_of)
        clients = ClientIntelligenceEngine().evaluate_portfolio((), as_of=self.as_of)
        review = self.builder.build(commercial, clients, ())

        with self.assertRaisesRegex(ValueError, "positive"):
            review.render(max_items_per_section=0)


if __name__ == "__main__":
    unittest.main()
