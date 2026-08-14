from __future__ import annotations

import unittest

from runtime.tony_agency_focus import TonyAgencyFocusCommandService
from runtime.tony_command_service import CommandResponse


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, morning_data=None, morning_status="healthy") -> None:
        self.morning_data = morning_data or {}
        self.morning_status = morning_status
        self.calls = []

    def execute(self, command, objects):
        self.calls.append(command)
        if command == "morning":
            return CommandResponse("morning", self.morning_status, "brief", self.morning_data)
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyAgencyFocusTests(unittest.TestCase):
    def test_client_blocker_outranks_positive_reply_and_platform_work(self):
        inner = StubCommandService(
            {
                "agency_state": {
                    "executive_items": [
                        {
                            "item_id": "client-risk",
                            "area": "clients",
                            "title": "Client renewal at risk",
                            "blocked": True,
                            "requires_matt": True,
                            "next_action": "Call the client today and resolve the delivery concern.",
                        },
                        {
                            "item_id": "infra",
                            "area": "infrastructure",
                            "title": "Runtime deployment needs attention",
                            "blocked": True,
                            "requires_matt": True,
                            "next_action": "Repair the deployment wrapper.",
                        },
                    ]
                },
                "commercial_watch": {
                    "positive_replies": [
                        {
                            "lead_id": "lesley",
                            "contact": "Lesley",
                            "company": "Harman Communications",
                            "recommended_next_action": "Move the opportunity to discovery.",
                        }
                    ],
                    "overdue": [],
                },
            }
        )
        service = TonyAgencyFocusCommandService(inner)

        response = service.execute("What should I focus on today?", [])

        self.assertEqual(response.command, "agency_focus")
        self.assertEqual(response.data["priorities"][0]["reason"], "current_revenue_or_delivery_risk")
        self.assertIn("Client renewal at risk", response.message)
        self.assertIn("positive reply from Lesley", response.message)
        self.assertNotIn("Runtime deployment", response.message)
        self.assertIn("leave engineering or infrastructure work alone", response.message)

    def test_positive_reply_outranks_overdue_follow_up_and_routine_work(self):
        inner = StubCommandService(
            {
                "agency_state": {
                    "executive_items": [
                        {
                            "item_id": "delivery",
                            "area": "delivery",
                            "title": "Prepare client workshop",
                            "blocked": False,
                            "requires_matt": False,
                            "next_action": "Finish the workshop structure.",
                        }
                    ]
                },
                "commercial_watch": {
                    "positive_replies": [
                        {
                            "lead_id": "jimmy",
                            "contact": "Jimmy",
                            "company": "Jimmy Diamond Ltd",
                            "recommended_next_action": "Review the reply and decide whether to book discovery.",
                        }
                    ],
                    "overdue": [
                        {
                            "commitment_id": "follow-up:lesley",
                            "lead_id": "lesley",
                            "contact": "Lesley",
                            "company": "Harman Communications",
                            "due_on": "2026-08-13",
                        }
                    ],
                },
            }
        )
        service = TonyAgencyFocusCommandService(inner)

        response = service.execute("What matters most right now?", [])

        priorities = response.data["priorities"]
        self.assertEqual(priorities[0]["reason"], "new_positive_commercial_intent")
        self.assertEqual(priorities[1]["reason"], "overdue_commercial_commitment")
        self.assertEqual(priorities[2]["reason"], "business_priority")
        self.assertIn("Your first priority is the positive reply from Jimmy", response.message)

    def test_focus_query_falls_back_to_commercial_creation_when_no_verified_priority_exists(self):
        inner = StubCommandService({"agency_state": {"executive_items": []}, "commercial_watch": {}})
        service = TonyAgencyFocusCommandService(inner)

        response = service.execute("Where should I focus?", [])

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["priorities"], [])
        self.assertIn("create or advance a commercial opportunity", response.message)

    def test_unrelated_command_delegates_unchanged(self):
        inner = StubCommandService()
        service = TonyAgencyFocusCommandService(inner)

        response = service.execute("Tell me about Lesley", [])

        self.assertEqual(response.command, "delegated")
        self.assertEqual(inner.calls, ["Tell me about Lesley"])


if __name__ == "__main__":
    unittest.main()
