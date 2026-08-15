from __future__ import annotations

import unittest

from runtime.tony_agency_focus import TonyAgencyFocusCommandService
from runtime.tony_command_service import CommandResponse
from runtime.tony_tool_routing import TonyExecutiveToolRouter


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, morning_data=None) -> None:
        self.morning_data = morning_data or {}
        self.calls = []

    def execute(self, command, objects):
        self.calls.append(command)
        if command == "morning":
            return CommandResponse("morning", "healthy", "brief", self.morning_data)
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyExecutiveToolRouterTests(unittest.TestCase):
    def test_routes_website_implementation_to_replit(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "operations",
                "label": "Fix the Growth Diagnostic landing page",
                "action": "Update the website CTA and landing page flow.",
                "target": {"item_id": "website-cta"},
            }
        )

        self.assertEqual(handoff["worker"], "Replit")
        self.assertEqual(handoff["then_owner"], "Tony")
        self.assertTrue(handoff["approval_required"])
        self.assertEqual(handoff["execution_truth"], "handoff_prepared_only")
        self.assertIn("website", handoff["routing_reason"])

    def test_routes_workflow_change_to_n8n(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "automation",
                "label": "Repair lead enrichment workflow",
                "action": "Update the n8n workflow so qualified leads reach Notion.",
            }
        )

        self.assertEqual(handoff["worker"], "n8n")
        self.assertIn("workflow", handoff["routing_reason"])

    def test_routes_record_action_to_notion_before_generic_claude(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "operations",
                "label": "Commercial record hygiene",
                "action": "Update the lead status in Notion after verified evidence.",
            }
        )

        self.assertEqual(handoff["worker"], "Notion")
        self.assertIn("authoritative workspace state", handoff["action"])

    def test_defaults_reasoning_and_drafting_to_claude(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "delivery",
                "label": "Prepare the client proposition",
                "action": "Develop the strategic recommendation and draft the client brief.",
            }
        )

        self.assertEqual(handoff["worker"], "Claude")
        self.assertIn("reasoning", handoff["routing_reason"])

    def test_agency_focus_uses_router_for_top_non_matt_priority(self):
        inner = StubCommandService(
            {
                "agency_state": {
                    "executive_items": [
                        {
                            "item_id": "site-conversion",
                            "area": "operations",
                            "title": "Growth Diagnostic conversion",
                            "blocked": False,
                            "requires_matt": False,
                            "next_action": "Update the website landing page CTA and form flow.",
                        }
                    ]
                },
                "commercial_watch": {},
            }
        )
        service = TonyAgencyFocusCommandService(inner)

        service.execute("What should I focus on today?", [])
        response = service.execute("OK, do the first one", [])

        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Replit")
        self.assertEqual(handoff["target"]["item_id"], "site-conversion")
        self.assertEqual(handoff["execution_truth"], "handoff_prepared_only")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("Replit", response.message)
        self.assertEqual(inner.calls, ["morning"])


if __name__ == "__main__":
    unittest.main()
