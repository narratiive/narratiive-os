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

    def service(
        self,
        *,
        body: str | None = None,
        subject: str | None = None,
        invitation: dict | None = None,
    ):
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
                            "recipient_email": "alex@example.com",
                            "area": "commercial",
                        },
                    },
                    "evidence": {
                        "email_subject": self.SUBJECT if subject is None else subject,
                        "email_body": self.BODY if body is None else body,
                        "creative_brief": "Create one restrained visual treatment that dramatises the gap between a complex offer and a clear commercial story without inventing product claims.",
                        **({"discovery_invitation": invitation} if invitation is not None else {}),
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
            discovery_booking_url="https://calendar.app.google/example",
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
        self.assertIn("Hi Alex", handoff["dispatch"]["instruction"])
        self.assertIn("exactly as reviewed", handoff["dispatch"]["instruction"])
        payload = handoff["dispatch"]["payload"]
        self.assertEqual(payload["kind"], "reviewed_outreach_email")
        self.assertEqual(payload["subject"], self.SUBJECT)
        self.assertEqual(payload["body"], self.BODY)
        self.assertIn("restrained visual treatment", payload["creative_brief"])
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

    def test_groundwork_invitation_adds_html_and_routes_only_to_an_unsent_gmail_draft(self):
        sources = [
            {"label": "About", "url": "https://example.com/about"},
            {"label": "Impact", "url": "https://example.com/impact"},
            {"label": "Wholesale", "url": "https://example.com/wholesale"},
        ]
        invitation = {
            "company_name": "Example Co",
            "first_name": "Alex",
            "email_subject": self.SUBJECT,
            "headline_lines": ["Example Co —", "what could the", "next chapter hold?"],
            "intro_paragraphs": [
                "We have been looking at Example Co's public growth story and are intrigued by the next strategic choice.",
                "The opportunity may be to turn existing substance into sharper reasons for different audiences to choose.",
            ],
            "brand_visual_url": "https://example.com/brand.jpg?v=1",
            "brand_visual_alt": "Example Co public brand image",
            "groundwork_sources": sources,
            "conversation_starters": [
                {"heading": "WHICH GROWTH MATTERS MOST?", "body": "Which audience is the priority now?", "source_urls": [sources[0]["url"]]},
                {"heading": "WHAT SHOULD WORK HARDER?", "body": "How could verified proof become more commercially useful?", "source_urls": [sources[1]["url"]]},
                {"heading": "WHAT MUST REMAIN DISTINCTIVE?", "body": "Could scale strengthen the brand rather than flatten it?", "source_urls": [sources[2]["url"]]},
            ],
        }
        service = self.service(invitation=invitation)

        review = service.execute("What do you recommend?", [])
        judgement = review.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "outreach_package_ready")
        self.assertTrue(judgement["review_checks"]["groundwork_evidence_bound"])
        self.assertTrue(judgement["review_checks"]["html_rendered"])
        self.assertIn("unsent Gmail draft", judgement["recommended_next_action"])

        handoff = service.execute("OK, do that", []).data["execution_handoff"]
        payload = handoff["dispatch"]["payload"]
        self.assertEqual(handoff["worker"], "Gmail")
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
        self.assertEqual(payload["operation"], "create_draft")
        self.assertEqual(payload["recipient_email"], "alex@example.com")
        self.assertIn("background:#f3efe8", payload["email_html"])
        self.assertIn("calendar.app.google/example", payload["email_html"])
        self.assertFalse(handoff["dispatch"].get("sent", False))


if __name__ == "__main__":
    unittest.main()
