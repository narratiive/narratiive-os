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
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
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
        self.assertTrue(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
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
        self.assertTrue(handoff["approval_required"])
        self.assertIn("authoritative workspace state", handoff["action"])

    def test_defaults_reasoning_and_drafting_to_claude_without_approval(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "delivery",
                "label": "Prepare the client proposition",
                "action": "Develop the strategic recommendation and draft the client brief.",
            }
        )

        self.assertEqual(handoff["worker"], "Claude")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertIn("reversible", handoff["approval_reason"])
        self.assertIn("reasoning", handoff["routing_reason"])

    def test_gmail_thread_read_is_autonomous_but_send_is_approval_gated(self):
        router = TonyExecutiveToolRouter()
        read_handoff = router.route(
            {
                "area": "commercial",
                "label": "Check Lesley's reply",
                "action": "Retrieve the verified email thread and assess the reply.",
            }
        )
        send_handoff = router.route(
            {
                "area": "commercial",
                "label": "Reply to Lesley",
                "action": "Send the approved follow-up email.",
            }
        )

        self.assertEqual(read_handoff["worker"], "Gmail")
        self.assertFalse(read_handoff["approval_required"])
        self.assertEqual(read_handoff["execution_mode"], "autonomous_read")
        self.assertEqual(send_handoff["worker"], "Gmail")
        self.assertTrue(send_handoff["approval_required"])
        self.assertEqual(send_handoff["execution_mode"], "approval_gated_write")

    def test_calendar_availability_check_is_autonomous_but_booking_is_gated(self):
        router = TonyExecutiveToolRouter()
        read_handoff = router.route(
            {
                "area": "operations",
                "label": "Find time for discovery",
                "action": "Check calendar availability for next week.",
            }
        )
        book_handoff = router.route(
            {
                "area": "operations",
                "label": "Book discovery",
                "action": "Book the meeting for Tuesday morning.",
            }
        )

        self.assertEqual(read_handoff["worker"], "Google Calendar")
        self.assertFalse(read_handoff["approval_required"])
        self.assertEqual(read_handoff["execution_mode"], "autonomous_read")
        self.assertTrue(book_handoff["approval_required"])
        self.assertEqual(book_handoff["execution_mode"], "approval_gated_write")

    def test_stateful_platform_inspection_can_proceed_without_write_approval(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "engineering",
                "label": "Repository health",
                "action": "Inspect the GitHub test suite and summarise the failing checks.",
            }
        )

        self.assertEqual(handoff["worker"], "GitHub")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_read")

    def test_ambiguous_stateful_action_fails_conservatively(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "operations",
                "label": "Notion workspace",
                "action": "Handle the Notion workspace item.",
            }
        )

        self.assertEqual(handoff["worker"], "Notion")
        self.assertTrue(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
        self.assertIn("ambiguous", handoff["approval_reason"])

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
        self.assertTrue(handoff["approval_required"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("Replit", response.message)
        self.assertEqual(inner.calls, ["morning"])

    def test_agency_focus_can_prepare_internal_reasoning_without_approval(self):
        inner = StubCommandService(
            {
                "agency_state": {
                    "executive_items": [
                        {
                            "item_id": "client-proposition",
                            "area": "delivery",
                            "title": "Client proposition",
                            "blocked": False,
                            "requires_matt": False,
                            "next_action": "Develop the strategic recommendation and draft the client brief.",
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
        self.assertEqual(handoff["worker"], "Claude")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertNotIn("irreversible change remains behind your approval", response.message)


if __name__ == "__main__":
    unittest.main()
