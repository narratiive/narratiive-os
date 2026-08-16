from __future__ import annotations

import unittest

from runtime.inbound_leads import InboundLead
from runtime.tony_agency_focus import TonyAgencyFocusCommandService
from runtime.tony_command_service import CommandResponse


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, lead: InboundLead) -> None:
        self.lead = lead

    def execute(self, command, objects):
        if command != "morning":
            return CommandResponse("delegated", "healthy", "delegated", {})
        item = self.lead.to_agency_item().to_dict()
        return CommandResponse(
            "morning", "healthy", "brief",
            {"agency_state": {"executive_items": [item]}, "commercial_watch": {"positive_replies": [], "overdue": []}},
        )


class TonyInboundResearchHandoffTests(unittest.TestCase):
    def test_new_inbound_lead_research_prepares_evidence_grounded_growth_blueprint(self) -> None:
        lead = InboundLead.from_mapping({
            "id": "lead-1", "Contact": "Jamie Example", "Company": "Example Co", "Source": "Tally",
            "Notes": "We have grown quickly but our positioning and marketing are fragmented.",
        })
        action = lead.recommended_next_action
        self.assertIn("Research Example Co", action)
        self.assertIn("verified sources", action)
        self.assertIn("source-backed evidence", action)
        self.assertIn("Growth Blueprint", action)
        self.assertIn("assumptions and evidence gaps", action)
        self.assertIn("advance, revise, or stop", action)
        self.assertNotIn("Opportunity Card", action)

        service = TonyAgencyFocusCommandService(StubCommandService(lead))
        focus = service.execute("What should I focus on today?", ())
        self.assertIn("New lead: Jamie Example — Example Co", focus.message)

        response = service.execute("OK, do that", ())
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Claude")
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertFalse(handoff["approval_required"])
        self.assertTrue(handoff["dispatch"]["eligible"])
        self.assertEqual(handoff["dispatch"]["state"], "ready_for_autonomous_dispatch")
        instruction = handoff["dispatch"]["instruction"]
        self.assertIn("Research Example Co", instruction)
        self.assertIn("source-backed evidence", instruction)
        self.assertIn("first-pass Growth Blueprint", instruction)
        self.assertIn("Do not send anything or change external state", instruction)
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
