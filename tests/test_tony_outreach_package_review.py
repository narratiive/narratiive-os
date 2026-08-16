from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyOutreachPackageReviewTests(unittest.TestCase):
    NOW = datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc)
    SUBJECT = "A sharper growth story for Example Co"
    BODY = (
        "Hi Alex, I have been looking at how Example Co is presenting its growth story and there is a strong business underneath it, "
        "but the positioning currently asks prospects to join too many dots for themselves. Narratiive could help turn that complexity into one clearer "
        "commercial narrative and a more distinctive route into demand generation. I have mapped the opportunity from the evidence available and would be "
        "happy to share the thinking if useful. Best, Matt"
    )

    def service(self, *, body: str | None = None, subject: str | None = None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Path(tmp.name) / "result.json"
        store.write_text(
            json.dumps(
                {
                    "worker": "Claude",
                    "dispatch": {
                        "worker": "Claude",
                        "execution_mode": "autonomous_prepare",
                        "instruction": (
                            "Prepare a tailored outreach package for Alex Example using only the reviewed Growth Blueprint and verified evidence. "
                            "Return a concise email subject and body plus any supporting personalised creative brief that materially strengthens the approach. "
                            "Preserve evidence gaps and do not invent claims. Do not send the email, update Notion, create a calendar event, or change any external state."
                        ),
                        "target": {
                            "lead_id": "lead-1",
                            "contact": "Alex Example",
                            "area": "commercial",
                        },
                    },
                    "evidence": {
                        "email_subject": self.SUBJECT if subject is None else subject,
                        "email_body": self.BODY if body is None else body,
                        "creative_brief": "Create one restrained visual treatment that dramatises the gap between a complex offer and a clear commercial story without inventing product claims.",
                    },
                    "executive_result": "Claude returned the tailored outreach package.",
                    "verified_at": self.NOW.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        return TonyCommercialAutonomousJudgementCommandService(
            StubCommandService(),
            store_path=store,
            clock=lambda: self.NOW,
        )

    def test_strong_outreach_is_reviewed_then_exact_email_is_approval_gated_for_gmail(self):
        service = self.service()

        review = service.execute("What do you recommend?", [])
        judgement = review.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "outreach_package_ready")
        self.assertEqual(judgement["review_status"], "ready_for_approval")
        self.assertTrue(all(judgement["review_checks"].values()))
        self.assertIn("final approval", review.message)
        self.assertIn("Nothing has been sent externally", review.message)

        response = service.execute("OK, send it", [])
        self.assertEqual(response.command, "autonomous_result_action")
        self.assertEqual(response.data["execution_status"], "approved_for_execution")
        handoff = response.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Gmail")
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
        self.assertTrue(handoff["approval_required"])
        self.assertTrue(handoff["approval_granted"])
        self.assertIn(self.SUBJECT, handoff["action"])
        self.assertIn(self.BODY, handoff["dispatch"]["instruction"])
        self.assertIn("exactly as reviewed", handoff["dispatch"]["instruction"])
        self.assertFalse(response.data["external_action_taken"])

    def test_weak_outreach_is_routed_to_revision_and_never_exposes_send_action(self):
        service = self.service(body="Generic note with no recipient context.", subject="Hello")

        review = service.execute("What do you recommend?", [])
        judgement = review.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "outreach_package_revision_required")
        self.assertEqual(judgement["review_status"], "revision_required")
        self.assertIn("contact specific", judgement["failed_checks"])
        self.assertIn("body substantive", judgement["failed_checks"])
        self.assertIn("subject concise", judgement["failed_checks"])
        self.assertIn("would not send it yet", review.message)
        self.assertNotIn("Send the following reviewed outreach email", judgement["execution_next_action"])


if __name__ == "__main__":
    unittest.main()
