import unittest

from runtime.agency_state import AgencyArea
from runtime.agency_state_projection import AgencyStateProjector
from runtime.inbound_leads import InboundLead
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus


class AgencyStateProjectionTests(unittest.TestCase):
    def test_unavailable_lead_source_does_not_claim_pipeline_is_empty(self):
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

        self.assertEqual(state.items_for(AgencyArea.COMMERCIAL), ())
        lead_feed = state.items_for(AgencyArea.AUTOMATION)
        self.assertEqual(len(lead_feed), 1)
        self.assertIn("Inbound lead feed unavailable", lead_feed[0].title)
        self.assertFalse(lead_feed[0].blocks_agency_outcome)
        self.assertFalse(lead_feed[0].blocked)

    def test_connected_empty_lead_source_creates_truthful_commercial_empty_state(self):
        snapshot = MissionControlSnapshot(
            generated_at="2026-07-29T08:00:00Z",
            status="healthy",
            progress={"status": "healthy"},
            workstreams=(),
            connections=(),
            approvals_required=(),
            blockers=(),
        )

        state = AgencyStateProjector().project(snapshot, lead_source_available=True)

        commercial = state.items_for(AgencyArea.COMMERCIAL)
        self.assertEqual(len(commercial), 1)
        self.assertIn("No active lead", commercial[0].title)

    def test_live_new_lead_is_visible_as_commercial_work(self):
        snapshot = MissionControlSnapshot(
            generated_at="2026-08-12T18:00:00Z",
            status="healthy",
            progress={"status": "healthy"},
            workstreams=(),
            connections=(),
            approvals_required=(),
            blockers=(),
        )
        steve = InboundLead(
            lead_id="3ba0c9cf-a8f2-81fd-b685-daf07e5feb4c",
            contact="Steve",
            company="Steve Company",
            email="steve@stevemail.com",
            source="Growth Diagnostic",
            status="New",
            pipeline_stage="New Diagnostic",
            lead_temperature="Warm",
            recommended_next_action="Review diagnostic and prepare Narratiive Opportunity Card.",
        )

        state = AgencyStateProjector().project(
            snapshot,
            (steve,),
            lead_source_available=True,
        )

        commercial = state.items_for(AgencyArea.COMMERCIAL)
        self.assertEqual(len(commercial), 1)
        self.assertIn("New lead: Steve — Steve Company", commercial[0].title)
        self.assertIn("Growth Diagnostic", commercial[0].title)
        self.assertIn("Warm", commercial[0].title)
        self.assertEqual(
            commercial[0].next_action,
            "Review diagnostic and prepare Narratiive Opportunity Card.",
        )

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

    def test_mission_control_maintenance_stays_in_background(self):
        snapshot = MissionControlSnapshot(
            generated_at="2026-07-29T08:00:00Z",
            status="healthy",
            progress={"status": "healthy"},
            workstreams=(
                WorkstreamStatus(
                    "mission-control-maintenance",
                    "Mission Control",
                    "functional",
                    "Tony",
                    "Use the recorded snapshot",
                ),
            ),
            connections=(),
            approvals_required=(),
            blockers=(),
        )

        state = AgencyStateProjector().project(snapshot)
        item = next(item for item in state.items if item.item_id == "mission-control-maintenance")

        self.assertEqual(item.area, AgencyArea.ENGINEERING)
        self.assertFalse(item.executive_visible)

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
