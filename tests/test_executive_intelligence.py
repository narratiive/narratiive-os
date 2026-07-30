import unittest

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.executive_intelligence import ExecutiveIntelligenceService


class ExecutiveIntelligenceTests(unittest.TestCase):
    def test_commercial_and_client_work_rank_before_internal_platform_work(self):
        state = AgencyState.from_items(
            "2026-07-30T08:00:00Z",
            (
                AgencyItem("eng-1", AgencyArea.ENGINEERING, "Runtime refactor", "active", "Continue refactor."),
                AgencyItem("client-1", AgencyArea.CLIENTS, "Client proposal", "active", "Send the proposal."),
                AgencyItem("commercial-1", AgencyArea.COMMERCIAL, "Qualified lead", "active", "Book the discovery call."),
            ),
        )

        direction = ExecutiveIntelligenceService().analyse(state)

        self.assertEqual([item.item_id for item in direction.focus], ["commercial-1", "client-1"])
        self.assertEqual(direction.recommendation, "Book the discovery call.")

    def test_matt_decision_becomes_first_focus(self):
        state = AgencyState.from_items(
            "2026-07-30T08:00:00Z",
            (
                AgencyItem("commercial-1", AgencyArea.COMMERCIAL, "Prospecting", "active", "Send introductions."),
                AgencyItem(
                    "client-1",
                    AgencyArea.CLIENTS,
                    "Pricing decision",
                    "waiting",
                    "Approve the proposed fee.",
                    requires_matt=True,
                ),
            ),
        )

        direction = ExecutiveIntelligenceService().analyse(state)

        self.assertEqual(direction.focus[0].item_id, "client-1")
        self.assertEqual(direction.matt_decisions[0].item_id, "client-1")
        self.assertEqual(direction.recommendation, "Approve the proposed fee.")

    def test_only_material_matt_dependencies_interrupt(self):
        state = AgencyState.from_items(
            "2026-07-30T08:00:00Z",
            (
                AgencyItem(
                    "client-1",
                    AgencyArea.CLIENTS,
                    "Routine preference",
                    "waiting",
                    "Choose option A or B.",
                    requires_matt=True,
                ),
                AgencyItem(
                    "delivery-1",
                    AgencyArea.DELIVERY,
                    "Launch approval",
                    "blocked",
                    "Approve launch today.",
                    blocked=True,
                    blocks_agency_outcome=True,
                    requires_matt=True,
                ),
            ),
        )

        direction = ExecutiveIntelligenceService().analyse(state)

        self.assertEqual([item.item_id for item in direction.interruptions], ["delivery-1"])

    def test_tony_handles_non_matt_work_without_escalating_it(self):
        state = AgencyState.from_items(
            "2026-07-30T08:00:00Z",
            (
                AgencyItem("ops-1", AgencyArea.OPERATIONS, "Prepare brief", "active", "Draft the brief."),
                AgencyItem("auto-1", AgencyArea.AUTOMATION, "Check workflow", "active", "Verify the workflow."),
            ),
        )

        direction = ExecutiveIntelligenceService().analyse(state)

        self.assertEqual([item.item_id for item in direction.tony_handles], ["ops-1", "auto-1"])
        self.assertEqual(direction.matt_decisions, ())
        self.assertEqual(direction.interruptions, ())


if __name__ == "__main__":
    unittest.main()
