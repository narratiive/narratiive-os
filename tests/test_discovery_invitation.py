from __future__ import annotations

import unittest

from runtime.discovery_invitation import (
    DiscoveryInvitationError,
    TEMPLATE_VERSION,
    render_discovery_invitation,
)


class DiscoveryInvitationTests(unittest.TestCase):
    def invitation(self):
        sources = [
            {"label": "About", "url": "https://example.com/about?view=story"},
            {"label": "Impact", "url": "https://example.com/impact"},
            {"label": "Wholesale", "url": "https://example.com/wholesale"},
        ]
        return {
            "company_name": "Synthetic Coffee",
            "first_name": "Alex",
            "email_subject": "Synthetic Coffee — what could the next chapter hold?",
            "headline_lines": ["Synthetic Coffee —", "what could the", "next chapter hold?"],
            "intro_paragraphs": [
                "We have been looking at Synthetic Coffee's public growth story and are intrigued by the next strategic choice.",
                "The opportunity may be less about another claim and more about turning existing substance into sharper reasons to choose.",
            ],
            "brand_visual_url": "https://example.com/images/coffee.jpg?v=1",
            "brand_visual_alt": "Synthetic Coffee wholesale experience",
            "groundwork_sources": sources,
            "conversation_starters": [
                {
                    "heading": "WHICH KIND OF GROWTH MATTERS MOST NOW?",
                    "body": "Which audience is the priority, and what would meaningful progress look like?",
                    "source_urls": [sources[0]["url"]],
                },
                {
                    "heading": "HOW DOES PURPOSE BECOME COMMERCIAL PROOF?",
                    "body": "How could verified credentials work harder as reasons to trust and choose?",
                    "source_urls": [sources[1]["url"]],
                },
                {
                    "heading": "CAN SCALE STRENGTHEN DISTINCTIVENESS?",
                    "body": "Could one coherent platform grow different routes without flattening the brand?",
                    "source_urls": [sources[2]["url"]],
                },
            ],
        }

    def test_renders_approved_design_and_matching_plain_text_from_groundwork(self):
        rendered = render_discovery_invitation(
            self.invitation(),
            booking_url="https://calendar.app.google/example?utm_source=narratiive",
        )

        self.assertEqual(rendered.template_version, TEMPLATE_VERSION)
        self.assertIn("background:#f3efe8", rendered.email_html)
        self.assertIn("background:#e4602e", rendered.email_html)
        self.assertIn("font-family:Georgia", rendered.email_html)
        self.assertIn("@media screen and (max-width:620px)", rendered.email_html)
        self.assertIn("Synthetic Coffee —<br>what could the<br>next chapter hold?", rendered.email_html)
        self.assertIn("https://calendar.app.google/example?utm_source=narratiive", rendered.email_html)
        self.assertIn("WHICH KIND OF GROWTH MATTERS MOST NOW?", rendered.body)
        self.assertIn("No pitch deck. No obligation.", rendered.body)
        self.assertNotIn("https://example.com/impact", rendered.email_html)

    def test_missing_or_unverified_groundwork_personalisation_fails_closed(self):
        invitation = self.invitation()
        invitation["conversation_starters"][0]["source_urls"] = ["https://invented.example/claim"]
        with self.assertRaisesRegex(DiscoveryInvitationError, "not present in Groundwork"):
            render_discovery_invitation(
                invitation,
                booking_url="https://calendar.app.google/example",
            )

    def test_unsafe_or_non_calendar_urls_are_rejected(self):
        invitation = self.invitation()
        invitation["brand_visual_url"] = "http://127.0.0.1/private.jpg"
        with self.assertRaisesRegex(DiscoveryInvitationError, "public host"):
            render_discovery_invitation(
                invitation,
                booking_url="https://calendar.app.google/example",
            )
        with self.assertRaisesRegex(DiscoveryInvitationError, "Google Calendar"):
            render_discovery_invitation(
                self.invitation(),
                booking_url="https://example.com/book",
            )


if __name__ == "__main__":
    unittest.main()
