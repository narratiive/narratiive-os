from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response

    def execute(self, command, objects):
        return self.response


def commercial_read_response() -> CommandResponse:
    return CommandResponse(
        command="agency_focus_action",
        status="healthy",
        message="Commercial evidence check prepared.",
        data={
            "execution_handoff": {
                "worker": "Gmail",
                "approval_required": False,
                "execution_truth": "handoff_prepared_only",
                "dispatch": {
                    "eligible": True,
                    "state": "ready_for_autonomous_dispatch",
                    "worker": "Gmail",
                    "instruction": "review the verified reply email thread for this lead",
                    "target": {"lead_id": "lesley", "area": "commercial"},
                    "execution_mode": "autonomous_read",
                    "expected_evidence": "decision-grade commercial read",
                    "return_to": "Tony",
                    "execution_truth": "not_dispatched",
                },
            }
        },
    )


class TonyCommercialAutonomousJudgementTests(unittest.TestCase):
    def service(self, evidence):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return TonyCommercialAutonomousJudgementCommandService(
            StubCommandService(commercial_read_response()),
            dispatchers={"Gmail": lambda contract: evidence},
            store_path=Path(tmp.name) / "result.json",
        )

    def test_positive_reply_becomes_tony_owned_discovery_recommendation(self):
        service = self.service(
            {
                "thread_id": "thread-1",
                "read_only": True,
                "summary": "Lesley is interested and asked for our availability next week.",
                "recommended_next_action": "Discount the work by 50%.",
            }
        )

        response = service.execute("do the first one", [])

        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "positive_intent")
        self.assertEqual(judgement["judgement_owner"], "Tony")
        self.assertIn("propose a discovery conversation", judgement["recommended_next_action"])
        self.assertNotIn("Discount", judgement["recommended_next_action"])
        self.assertIn("positive commercial intent", response.message)

        follow_up = service.execute("What do you recommend?", [])
        self.assertIn("propose a discovery conversation", follow_up.message)
        self.assertNotIn("Discount", follow_up.message)

    def test_decline_produces_close_record_recommendation(self):
        service = self.service(
            {
                "thread_id": "thread-2",
                "read_only": True,
                "content": "Thanks for reaching out, but we're not interested.",
            }
        )

        response = service.execute("do the first one", [])

        self.assertEqual(response.data["commercial_judgement"]["disposition"], "declined")
        self.assertIn("Update the lead record", response.data["commercial_judgement"]["recommended_next_action"])
        self.assertIn("this is a decline", response.message)

    def test_automatic_or_ambiguous_reply_does_not_invent_consequential_action(self):
        automatic = self.service(
            {
                "thread_id": "thread-3",
                "read_only": True,
                "summary": "Automatic reply: I am out of office until Monday.",
            }
        ).execute("do the first one", [])
        self.assertEqual(automatic.data["commercial_judgement"]["disposition"], "automatic_reply")
        self.assertEqual(automatic.data["commercial_judgement"]["recommended_next_action"], "")

        ambiguous_service = self.service(
            {
                "thread_id": "thread-4",
                "read_only": True,
                "summary": "Thanks for the note. I have passed this to my colleague.",
            }
        )
        ambiguous = ambiguous_service.execute("do the first one", [])
        self.assertEqual(ambiguous.data["commercial_judgement"]["disposition"], "reply_received")
        self.assertEqual(ambiguous.data["commercial_judgement"]["recommended_next_action"], "")
        recommendation = ambiguous_service.execute("What do you recommend?", [])
        self.assertIn("not enough grounded next-action evidence", recommendation.message)


if __name__ == "__main__":
    unittest.main()
