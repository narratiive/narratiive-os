import unittest

from runtime.agency_state import AgencyArea
from runtime.agency_state_projection import AgencyStateProjector
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus


class AgencyStateProjectionTests(unittest.TestCase):
    def test_empty_business_state_creates_commercial_priority(self):
        snapshot = MissionControlSnapshot(
            generated_at="2026-07-29T08:00:00Z",
            status="blocked",
            progress={"status": "blocked"},
            workstreams=(
                WorkstreamStatus(
                    "github-pr-104",
                    "PR 104 validation",
                    "blocked",
                    "Tony",
                    "Repair runtime validation",
                    blocker="failed check",
                ),
            ),
            connections=(),
            approvals_required=(),
            blockers=("github:pull_request:104:failed_check",),
        )

        state = AgencyStateProjector().project(snapshot)

        commercial = state.items_for(AgencyArea.COMMERCIAL)
        self.assertEqual(len(commercial), 1)
        self.assertIn("No qualified opportunity", commercial[0].title)
        self.assertEqual(len(state.hidden_platform_items), 1)
        self.assertEqual(state.agency_blockers, ())

    def test_business_work_is_classified_ahead_of_platform_work(self):
        snapshot = MissionControlSnapshot(
            generated_at="2026-07-29T08:00:00Z",
            status="healthy",
            progress={"status": "healthy"},
            workstreams=(
                WorkstreamStatus(
                    "lead-rave",
                    "Rave prospect follow-up",
                    "functional",
                    "Tony",
                    "Draft the tailored introduction",
                ),
                WorkstreamStatus(
                    "client-delivery",
                    "Client campaign delivery",
                    "functional",
                    "Tony",
                    "Complete the next deliverable",
                ),
                WorkstreamStatus(
                    "repo-maintenance",
                    "Repository validation",
                    "blocked",
                    "Tony",
                    "Repair the test suite",
                    blocker="failed check",
                ),
            ),
            connections=(),
            approvals_required=(),
            blockers=(),
        )

        state = AgencyStateProjector().project(snapshot)
        visible_areas = [item.area for item in state.executive_items]

        self.assertEqual(visible_areas[0], AgencyArea.COMMERCIAL)
        self.assertIn(AgencyArea.DELIVERY, visible_areas)
        self.assertNotIn(AgencyArea.ENGINEERING, visible_areas)

    def test_technical_issue_surfaces_only_with_business_consequence(self):
        snapshot = MissionControlSnapshot(
            generated_at="2026-07-29T08:00:00Z",
            status="blocked",
            progress={"status": "blocked"},
            workstreams=(
                WorkstreamStatus(
                    "lead-webhook",
                    "Lead webhook outage",
                    "blocked",
                    "Tony",
                    "Restore enquiry capture",
                    blocker="webhook unavailable",
                ),
            ),
            connections=(),
            approvals_required=(),
            blockers=(),
        )

        state = AgencyStateProjector().project(snapshot)
        item = next(item for item in state.items if item.item_id == "lead-webhook")

        self.assertTrue(item.executive_visible)
        self.assertTrue(item.blocks_agency_outcome)
        self.assertTrue(item.blocked)


if __name__ == "__main__":
    unittest.main()
