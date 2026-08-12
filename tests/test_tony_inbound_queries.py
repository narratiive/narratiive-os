from __future__ import annotations

import unittest
from datetime import datetime

from runtime.inbound_leads import InboundLead
from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self) -> None:
        self.calls = []

    def execute(self, command, objects):
        self.calls.append(command)
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyInboundQueryTests(unittest.TestCase):
    def setUp(self):
        self.paul = InboundLead(
            lead_id="paul",
            contact="Paul Thompson",
            company="thompsons",
            email="paul@thompson.com",
            source="Tally",
            status="New",
            pipeline_stage="New Diagnostic",
            lead_temperature="Warm",
            recommended_next_action="Review fit and decide whether to invite Paul to discovery.",
            created_at="2026-08-12T22:35:42Z",
            ai_summary="Thompsons reports stalled growth and declining order value.",
        )

    def service(self):
        return TonyExecutiveCommandService(
            StubCommandService(),
            inbound_lead_loader=lambda: (self.paul,),
            clock=lambda: datetime(2026, 8, 13, 0, 18),
        )

    def test_plain_language_yesterday_inbound_query_is_answered(self):
        response = self.service().execute("Summarise yesterday's inbound leads", [])

        self.assertEqual(response.command, "leads")
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["scope"], "yesterday")
        self.assertEqual(response.data["count"], 1)
        self.assertIn("Paul Thompson — thompsons", response.message)
        self.assertIn("Warm", response.message)
        self.assertIn("New Diagnostic", response.message)
        self.assertIn("declining order value", response.message)
        self.assertIn("Next:", response.message)

    def test_slash_leads_command_is_answered_without_mission_control(self):
        response = self.service().execute("/leads", [])

        self.assertEqual(response.command, "leads")
        self.assertEqual(response.data["count"], 1)

    def test_today_query_reports_truthful_empty_result(self):
        response = self.service().execute("today's leads", [])

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["count"], 0)
        self.assertIn("No inbound leads are recorded for today", response.message)


if __name__ == "__main__":
    unittest.main()
