from __future__ import annotations

import unittest

from runtime.autonomy_planner import AutonomyAction
from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleStage
from runtime.inbound_leads import InboundLead
from runtime.inbound_lifecycle import plan_inbound_autonomy, project_inbound_lead


def lead(stage: str, *, lead_id: str = "lead-1") -> InboundLead:
    return InboundLead(
        lead_id=lead_id,
        contact="Jamie Example",
        company="Example Co",
        email="jamie@example.com",
        source="Growth Diagnostic",
        status="New",
        pipeline_stage=stage,
        lead_temperature="Warm",
        recommended_next_action="Prepare the verified Blueprint Lite evidence package.",
        notion_url=f"https://notion.so/{lead_id}",
    )


class InboundLifecycleProjectionTests(unittest.TestCase):
    def test_new_diagnostic_stays_at_lead_until_progression_is_observed(self):
        record = project_inbound_lead(lead("New Diagnostic"))
        self.assertEqual(record.stage, ClientLifecycleStage.LEAD)
        self.assertEqual(record.client_id, "lead-1")
        self.assertEqual(record.client_name, "Example Co")
        self.assertEqual(record.owner, "Tony")
        self.assertEqual(record.next_action, "Prepare the verified Blueprint Lite evidence package.")
        self.assertIn("pipeline_stage:New Diagnostic", record.evidence)
        self.assertIn("notion:https://notion.so/lead-1", record.evidence)
        self.assertEqual(record.acquisition_path, AcquisitionPath.INBOUND)

    def test_known_pipeline_labels_map_to_existing_lifecycle_only(self):
        cases = {
            "Research": ClientLifecycleStage.RESEARCH,
            "Blueprint Lite": ClientLifecycleStage.BLUEPRINT_LITE,
            "Discovery": ClientLifecycleStage.MEETING,
            "Proposal": ClientLifecycleStage.PROPOSAL,
            "Delivery": ClientLifecycleStage.DELIVERY,
            "Invoice": ClientLifecycleStage.INVOICE,
            "Complete": ClientLifecycleStage.COMPLETE,
        }
        for pipeline_stage, expected in cases.items():
            with self.subTest(pipeline_stage=pipeline_stage):
                self.assertEqual(project_inbound_lead(lead(pipeline_stage)).stage, expected)

        self.assertEqual(
            project_inbound_lead(lead("Outreach")).acquisition_path,
            AcquisitionPath.LEGACY,
        )

    def test_unknown_pipeline_label_fails_safe_to_lead(self):
        self.assertEqual(
            project_inbound_lead(lead("Something Tony has never seen")).stage,
            ClientLifecycleStage.LEAD,
        )

    def test_new_diagnostic_enters_autonomous_internal_queue(self):
        plan = plan_inbound_autonomy((lead("New Diagnostic"),))
        self.assertEqual(len(plan.autonomous_queue), 1)
        self.assertEqual(plan.autonomous_queue[0].client_id, "lead-1")
        self.assertEqual(plan.autonomous_queue[0].action, AutonomyAction.CONTINUE)
        self.assertEqual(plan.human_queue, ())

    def test_discovery_and_proposal_are_human_gated_by_existing_policy(self):
        plan = plan_inbound_autonomy(
            (lead("Discovery", lead_id="discovery"), lead("Proposal", lead_id="proposal"))
        )
        self.assertEqual(plan.autonomous_queue, ())
        self.assertEqual(
            [item.client_id for item in plan.human_queue],
            ["discovery", "proposal"],
        )
        self.assertTrue(all(item.requires_human for item in plan.human_queue))


if __name__ == "__main__":
    unittest.main()
