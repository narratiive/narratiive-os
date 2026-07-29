import unittest

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage


class ClientLifecycleTests(unittest.TestCase):
    def test_canonical_stage_order_advances_one_step_at_a_time(self):
        lead = ClientLifecycleRecord(
            client_id="test-client",
            client_name="Test Client",
            stage=ClientLifecycleStage.LEAD,
            owner="Tony",
            next_action="Research the opportunity.",
            value_gbp=5000,
        )

        research = lead.advance(
            ClientLifecycleStage.RESEARCH,
            next_action="Create the research brief.",
        )

        self.assertEqual(research.stage, ClientLifecycleStage.RESEARCH)
        self.assertEqual(research.value_gbp, 5000)
        self.assertTrue(research.is_commercial)

    def test_skipping_a_stage_is_rejected(self):
        lead = ClientLifecycleRecord(
            client_id="test-client",
            client_name="Test Client",
            stage=ClientLifecycleStage.LEAD,
            owner="Tony",
            next_action="Research the opportunity.",
        )

        with self.assertRaisesRegex(ValueError, "invalid lifecycle transition"):
            lead.advance(
                ClientLifecycleStage.PROPOSAL,
                next_action="Create a proposal.",
            )

    def test_blocked_record_requires_a_specific_blocker(self):
        with self.assertRaisesRegex(ValueError, "require a blocker"):
            ClientLifecycleRecord(
                client_id="test-client",
                client_name="Test Client",
                stage=ClientLifecycleStage.MEETING,
                owner="Tony",
                next_action="Book the meeting.",
                blocked=True,
            )

    def test_delivery_and_finance_classification(self):
        delivery = ClientLifecycleRecord(
            client_id="test-client",
            client_name="Test Client",
            stage=ClientLifecycleStage.DELIVERY,
            owner="Tony",
            next_action="Deliver the Growth Blueprint.",
        )
        invoice = ClientLifecycleRecord(
            client_id="test-client",
            client_name="Test Client",
            stage=ClientLifecycleStage.INVOICE,
            owner="Matt",
            next_action="Issue the invoice.",
        )

        self.assertTrue(delivery.is_delivery)
        self.assertTrue(invoice.is_finance)
        self.assertFalse(invoice.is_commercial)


if __name__ == "__main__":
    unittest.main()
