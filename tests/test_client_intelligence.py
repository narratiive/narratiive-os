import unittest
from datetime import date
from decimal import Decimal

from runtime.client_intelligence import (
    ClientCommitment,
    ClientIntelligenceEngine,
    ClientRecord,
)


class ClientIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ClientIntelligenceEngine()
        self.as_of = date(2026, 8, 11)

    def test_healthy_client_preserves_momentum(self) -> None:
        client = ClientRecord(
            client_id="c1",
            name="Healthy Client",
            last_contact_on=date(2026, 8, 5),
            revenue_value=Decimal("5000"),
        )
        insight = self.engine.evaluate_client(client, as_of=self.as_of)
        self.assertEqual(insight.health, "healthy")
        self.assertEqual(insight.next_action, "Maintain momentum with Healthy Client")
        self.assertEqual(insight.reasons, ())

    def test_stale_contact_becomes_watch(self) -> None:
        client = ClientRecord(
            client_id="c2",
            name="Watch Client",
            last_contact_on=date(2026, 7, 20),
        )
        insight = self.engine.evaluate_client(client, as_of=self.as_of)
        self.assertEqual(insight.health, "watch")
        self.assertIn("no contact", insight.reasons[0])
        self.assertEqual(insight.next_action, "Re-engage Watch Client")

    def test_overdue_commitment_marks_client_at_risk(self) -> None:
        commitment = ClientCommitment(
            commitment_id="cm1",
            description="Send revised proposal",
            owner="Tony",
            due_on=date(2026, 8, 1),
        )
        client = ClientRecord(
            client_id="c3",
            name="At Risk Client",
            last_contact_on=date(2026, 8, 8),
            revenue_value=Decimal("12000"),
            commitments=(commitment,),
        )
        insight = self.engine.evaluate_client(client, as_of=self.as_of)
        self.assertEqual(insight.health, "at_risk")
        self.assertEqual(len(insight.overdue_commitments), 1)
        self.assertEqual(insight.next_action, "Close overdue commitment for At Risk Client")

    def test_blocked_commitment_requires_specific_blocker(self) -> None:
        with self.assertRaisesRegex(ValueError, "blocked commitment requires blocker"):
            ClientCommitment(
                commitment_id="cm2",
                description="Approve scope",
                owner="Matt",
                status="blocked",
            )

    def test_explicit_risk_and_next_action_are_preserved(self) -> None:
        client = ClientRecord(
            client_id="c4",
            name="Priority Client",
            last_contact_on=date(2026, 8, 10),
            risk_note="Renewal confidence has dropped",
            next_action="Call procurement today",
        )
        insight = self.engine.evaluate_client(client, as_of=self.as_of)
        self.assertEqual(insight.health, "at_risk")
        self.assertEqual(insight.next_action, "Call procurement today")
        self.assertIn("Renewal confidence has dropped", insight.reasons)

    def test_portfolio_prioritises_higher_value_at_risk_client(self) -> None:
        clients = (
            ClientRecord(
                client_id="low",
                name="Low Value",
                last_contact_on=date(2026, 7, 1),
                revenue_value=Decimal("2000"),
            ),
            ClientRecord(
                client_id="high",
                name="High Value",
                last_contact_on=date(2026, 7, 1),
                revenue_value=Decimal("15000"),
            ),
        )
        snapshot = self.engine.evaluate_portfolio(clients, as_of=self.as_of)
        self.assertEqual([item.client_id for item in snapshot.at_risk_clients], ["high", "low"])
        self.assertEqual(snapshot.revenue_value, Decimal("17000.00"))

    def test_duplicate_client_ids_fail_closed(self) -> None:
        client = ClientRecord(
            client_id="dup",
            name="Duplicate",
            last_contact_on=date(2026, 8, 10),
        )
        with self.assertRaisesRegex(ValueError, "duplicate client_id"):
            self.engine.evaluate_portfolio((client, client), as_of=self.as_of)

    def test_invalid_contact_thresholds_fail_closed(self) -> None:
        client = ClientRecord(
            client_id="c5",
            name="Threshold Client",
            last_contact_on=date(2026, 8, 10),
        )
        with self.assertRaisesRegex(ValueError, "contact_risk_days"):
            self.engine.evaluate_client(
                client,
                as_of=self.as_of,
                contact_watch_days=14,
                contact_risk_days=14,
            )


if __name__ == "__main__":
    unittest.main()
