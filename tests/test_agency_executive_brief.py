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

        self.assertIn("2. Commercial opportunities", output)
        self.assertIn("Create first qualified opportunity", output)
        self.assertNotIn("PR 104", output)
        self.assertIn("being handled in the background", output)
        self.assertEqual(brief.status, "healthy")

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
        self.assertIn("3. Delivery", output)
        self.assertIn("Webhook outage", output)
        self.assertIn("4. Decisions required", output)

    def test_main_brief_has_five_executive_sections_without_raw_evidence(self):
        state = AgencyState.from_items(
            "2026-07-29T08:00:00Z",
            (
                AgencyItem(
                    "lead-7",
                    AgencyArea.COMMERCIAL,
                    "FIELDWORK enquiry received",
                    "active",
                    "Review fit and decide whether to invite the prospect to DISCOVERY.",
                    evidence=("workflow:l6TysPR86l5VAoXc", "database_field:selected_service"),
                    why_matters="The prospect has stated a concrete service preference.",
                ),
            ),
        )

        output = AgencyExecutiveBriefService().build(state).render_compact()

        for heading in (
            "1. Agency status",
            "2. Commercial opportunities",
            "3. Delivery",
            "4. Decisions required",
            "5. Recommended priorities",
        ):
            self.assertIn(heading, output)
        self.assertNotIn("l6TysPR86l5VAoXc", output)
        self.assertNotIn("database_field", output)

    def test_long_delivery_detail_cannot_truncate_decisions_or_priorities(self):
        long_text = "Material delivery detail " * 80
        state = AgencyState.from_items(
            "2026-07-29T08:00:00Z",
            tuple(
                AgencyItem(
                    f"delivery-{index}",
                    AgencyArea.DELIVERY,
                    long_text,
                    "active",
                    long_text,
                    evidence=(f"source:{index}",),
                )
                for index in range(8)
            )
            + (
                AgencyItem(
                    "founder-decision",
                    AgencyArea.CLIENTS,
                    "Approve the exact client direction",
                    "decision_required",
                    "Approve or reject the exact client direction.",
                    requires_matt=True,
                    evidence=("approval:pending",),
                ),
            ),
        )

        output = AgencyExecutiveBriefService().build(state).render_compact()

        self.assertLessEqual(len(output), 3500)
        self.assertIn("4. Decisions required", output)
        self.assertIn("Approve the exact client direction", output)
        self.assertIn("5. Recommended priorities", output)

    def test_empty_agency_state_recommends_commercial_action_not_repository_work(self):
        state = AgencyState.from_items("2026-07-29T08:00:00Z", ())
        brief = AgencyExecutiveBriefService().build(state)

        self.assertEqual(brief.status, "healthy")
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
