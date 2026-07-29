import unittest

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.client_lifecycle_fixtures import deterministic_test_clients
from runtime.client_lifecycle_projection import ClientLifecycleProjector


class ClientLifecycleProjectionTests(unittest.TestCase):
    def test_lifecycle_records_replace_empty_commercial_state(self):
        state = AgencyState.from_items(
            "2026-07-29T12:00:00Z",
            (
                AgencyItem(
                    item_id="commercial-empty-state",
                    area=AgencyArea.COMMERCIAL,
                    title="No qualified opportunity currently recorded",
                    status="attention",
                    next_action="Create and progress the next qualified opportunity.",
                ),
            ),
        )

        enriched = ClientLifecycleProjector().enrich(state, deterministic_test_clients())
        ids = {item.item_id for item in enriched.items}

        self.assertNotIn("commercial-empty-state", ids)
        self.assertIn("client-northstar", ids)
        self.assertIn("client-fieldwork", ids)
        self.assertIn("client-signal-house", ids)

    def test_projection_surfaces_value_delivery_and_invoice_decision(self):
        state = AgencyState.from_items("2026-07-29T12:00:00Z", ())
        enriched = ClientLifecycleProjector().enrich(state, deterministic_test_clients())

        commercial = enriched.items_for(AgencyArea.COMMERCIAL)
        delivery = enriched.items_for(AgencyArea.DELIVERY)
        finance = enriched.items_for(AgencyArea.FINANCE)

        self.assertIn("£6,000", commercial[0].title)
        self.assertEqual(delivery[0].status, "delivery")
        self.assertEqual(finance[0].status, "invoice")
        self.assertTrue(finance[0].requires_matt)
        self.assertEqual(enriched.matt_actions[0].item_id, "client-signal-house")


if __name__ == "__main__":
    unittest.main()
