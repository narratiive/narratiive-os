import unittest

from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleRecord, ClientLifecycleStage


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
        blueprint_lite = research.advance(
            ClientLifecycleStage.BLUEPRINT_LITE,
            next_action="Route the evidence package to Claude for Blueprint Lite.",
        )

        self.assertEqual(research.stage, ClientLifecycleStage.RESEARCH)
        self.assertEqual(blueprint_lite.stage, ClientLifecycleStage.BLUEPRINT_LITE)
        self.assertEqual(blueprint_lite.value_gbp, 5000)
        self.assertTrue(blueprint_lite.is_commercial)

    def test_legacy_narrative_shift_state_maps_to_blueprint_lite(self):
        self.assertIs(ClientLifecycleStage("narrative_shift"), ClientLifecycleStage.BLUEPRINT_LITE)

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

    def test_inbound_and_outbound_paths_converge_at_discovery(self):
        inbound = ClientLifecycleRecord(
            client_id="inbound",
            client_name="Inbound Test",
            stage=ClientLifecycleStage.LEAD,
            owner="Tony",
            next_action="Prepare Blueprint Lite.",
            acquisition_path=AcquisitionPath.INBOUND,
        )
        outbound = ClientLifecycleRecord(
            client_id="outbound",
            client_name="Outbound Test",
            stage=ClientLifecycleStage.LEAD,
            owner="Tony",
            next_action="Research the target.",
            acquisition_path=AcquisitionPath.OUTBOUND,
        )

        inbound = inbound.advance(ClientLifecycleStage.BLUEPRINT_LITE, next_action="Prepare discovery.")
        inbound = inbound.advance(ClientLifecycleStage.MEETING, next_action="Run discovery.")
        outbound = outbound.advance(ClientLifecycleStage.RESEARCH, next_action="Prepare outreach.")
        outbound = outbound.advance(ClientLifecycleStage.OUTREACH, next_action="Secure discovery.")
        outbound = outbound.advance(ClientLifecycleStage.MEETING, next_action="Run discovery.")

        self.assertEqual(inbound.stage, ClientLifecycleStage.MEETING)
        self.assertEqual(outbound.stage, ClientLifecycleStage.MEETING)
        self.assertEqual(inbound.acquisition_path, AcquisitionPath.INBOUND)
        self.assertEqual(outbound.acquisition_path, AcquisitionPath.OUTBOUND)

    def test_path_specific_stage_is_rejected_fail_safe(self):
        with self.assertRaisesRegex(ValueError, "not valid for inbound"):
            ClientLifecycleRecord(
                client_id="inbound",
                client_name="Inbound Test",
                stage=ClientLifecycleStage.OUTREACH,
                owner="Tony",
                next_action="Do not infer progression.",
                acquisition_path=AcquisitionPath.INBOUND,
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
