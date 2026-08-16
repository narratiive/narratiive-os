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
            "morning",
            "healthy",
            "brief",
            {
                "agency_state": {"executive_items": [item]},
                "commercial_watch": {"positive_replies": [], "overdue": []},
            },
        )


class TonyInboundResearchHandoffTests(unittest.TestCase):
    def test_new_inbound_lead_defaults_to_autonomous_evidence_research(self) -> None:
        lead = InboundLead.from_mapping(
            {
                "id": "lead-1",
                "Contact": "Jamie Example",
                "Company": "Example Co",
                "Source": "Tally",
                "Notes": "We have grown quickly but our positioning and marketing are fragmented.",
            }
        )
        self.assertIn("Research Example Co", lead.recommended_next_action)
        self.assertIn("verified sources", lead.recommended_next_action)
        self.assertIn("evidence-backed recommendation", lead.recommended_next_action)
        self.assertNotIn("Opportunity Card", lead.recommended_next_action)

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
        self.assertIn("Research Example Co", handoff["action"])
        self.assertIn("evidence-backed recommendation", handoff["dispatch"]["instruction"])
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
