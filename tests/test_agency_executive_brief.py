import unittest

from runtime.agency_executive_brief import AgencyExecutiveBriefService
from runtime.agency_state import AgencyArea, AgencyItem, AgencyState


class AgencyExecutiveBriefTests(unittest.TestCase):
    def test_platform_work_is_hidden_when_it_does_not_block_agency_outcomes(self):
        state = AgencyState.from_items(
            "2026-07-29T08:00:00Z",
            (
                AgencyItem(
                    "pipeline-1",
                    AgencyArea.COMMERCIAL,
                    "Create first qualified opportunity",
                    "active",
                    "Send five tailored introductions.",
                ),
                AgencyItem(
                    "pr-104",
                    AgencyArea.ENGINEERING,
                    "PR 104 validation",
                    "failed",
                    "Repair the runtime validation check.",
                    blocked=True,
                ),
            ),
        )

        brief = AgencyExecutiveBriefService().build(state)
        output = brief.render_compact()

        self.assertIn("Commercial:", output)
        self.assertIn("Create first qualified opportunity", output)
        self.assertNotIn("PR 104", output)
        self.assertIn("being handled in the background", output)
        self.assertEqual(brief.status, "operational")

    def test_platform_work_surfaces_only_when_it_blocks_an_agency_outcome(self):
        state = AgencyState.from_items(
            "2026-07-29T08:00:00Z",
            (
                AgencyItem(
                    "automation-1",
                    AgencyArea.AUTOMATION,
                    "Lead response automation",
                    "blocked",
                    "Restore enquiry capture before the next campaign.",
                    blocked=True,
                    blocks_agency_outcome=True,
                ),
                AgencyItem(
                    "infra-1",
                    AgencyArea.INFRASTRUCTURE,
                    "Webhook outage",
                    "blocked",
                    "Restore the webhook used by enquiry capture.",
                    blocked=True,
                    blocks_agency_outcome=True,
                ),
            ),
        )

        brief = AgencyExecutiveBriefService().build(state)
        output = brief.render_compact()

        self.assertEqual(brief.status, "blocked")
        self.assertIn("Automation:", output)
        self.assertIn("Webhook outage", output)
        self.assertIn("Agency blockers:", output)

    def test_empty_agency_state_recommends_commercial_action_not_repository_work(self):
        state = AgencyState.from_items("2026-07-29T08:00:00Z", ())
        brief = AgencyExecutiveBriefService().build(state)

        self.assertEqual(brief.status, "operational")
        self.assertIn("commercial opportunity", brief.recommendation)
        self.assertNotIn("repository", brief.recommendation.casefold())

    def test_business_areas_are_ordered_before_engineering(self):
        state = AgencyState.from_items(
            "2026-07-29T08:00:00Z",
            (
                AgencyItem(
                    "engineering-1",
                    AgencyArea.ENGINEERING,
                    "Engineering issue",
                    "blocked",
                    "Resolve it.",
                    blocked=True,
                    requires_matt=True,
                ),
                AgencyItem(
                    "client-1",
                    AgencyArea.CLIENTS,
                    "Client decision",
                    "active",
                    "Confirm the next client action.",
                ),
                AgencyItem(
                    "commercial-1",
                    AgencyArea.COMMERCIAL,
                    "Pipeline action",
                    "active",
                    "Create the next opportunity.",
                ),
            ),
        )

        titles = [item.title for item in state.executive_items]
        self.assertEqual(titles, ["Pipeline action", "Client decision", "Engineering issue"])


if __name__ == "__main__":
    unittest.main()
