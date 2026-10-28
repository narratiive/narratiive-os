import unittest

from runtime.inbound_leads import InboundLead


class InboundLeadTests(unittest.TestCase):
    def test_accepts_entire_notion_create_page_payload_and_applies_inbound_defaults(self):
        payload = {
            "id": "3ba0c9cf-a8f2-819d-9846-ea44972a9f78",
            "url": "https://www.notion.so/3ba0c9cfa8f2819d9846ea44972a9f78",
            "created_time": "2026-08-12T22:35:42.392Z",
            "properties": {
                "Contact": {"title": [{"plain_text": "Paul Thompson"}]},
                "Company": {"rich_text": [{"plain_text": "thompsons"}]},
                "Email": {"email": "paul@thompson.com"},
                "Source": {"select": {"name": "Tally"}},
                "Status": {"status": {"name": "New"}},
                "Notes": {"rich_text": [{"plain_text": "We are busy but not getting customers and order value is declining."}]},
            },
        }
        lead = InboundLead.from_mapping(payload)
        self.assertEqual(lead.lead_id, payload["id"])
        self.assertEqual(lead.contact, "Paul Thompson")
        self.assertEqual(lead.company, "thompsons")
        self.assertEqual(lead.email, "paul@thompson.com")
        self.assertEqual(lead.source, "Tally")
        self.assertEqual(lead.status, "New")
        self.assertEqual(lead.pipeline_stage, "New Diagnostic")
        self.assertEqual(lead.lead_temperature, "Warm")
        self.assertIn("completed Growth Diagnostic", lead.recommended_next_action)
        self.assertIn("verified public sources", lead.recommended_next_action)
        self.assertIn("Claude", lead.recommended_next_action)
        self.assertIn("Blueprint Lite", lead.recommended_next_action)
        self.assertIn("facts, interpretations, and hypotheses", lead.recommended_next_action)
        self.assertNotIn("first-pass Growth Blueprint", lead.recommended_next_action)
        self.assertNotIn("Opportunity Card", lead.recommended_next_action)
        self.assertIn("thompsons submitted an inbound growth enquiry", lead.ai_summary)
        self.assertEqual(lead.created_at, "2026-08-12T22:35:42.392Z")

    def test_growth_diagnostic_source_routes_to_blueprint_lite(self):
        lead = InboundLead.from_mapping({
            "lead_id": "diagnostic-1",
            "contact": "Test Founder",
            "company": "Test Company",
            "source": "Growth Diagnostic",
            "notes": "Growth feels inconsistent and the story is unclear.",
        })
        self.assertEqual(lead.pipeline_stage, "New Diagnostic")
        self.assertEqual(lead.lead_temperature, "Warm")
        self.assertIn("Blueprint Lite", lead.recommended_next_action)
        self.assertIn("human review", lead.recommended_next_action)
        self.assertIn("execution evidence", lead.recommended_next_action)

    def test_explicit_commercial_judgement_is_never_overwritten(self):
        lead = InboundLead.from_mapping({
            "lead_id": "lead-1", "contact": "Jane Smith", "source": "Tally", "pipeline_stage": "Discovery Call",
            "lead_temperature": "Hot", "recommended_next_action": "Prepare for discovery.",
        })
        self.assertEqual(lead.pipeline_stage, "Discovery Call")
        self.assertEqual(lead.lead_temperature, "Hot")
        self.assertEqual(lead.recommended_next_action, "Prepare for discovery.")

    def test_website_fieldwork_preference_is_preserved_and_not_routed_to_groundwork(self):
        lead = InboundLead.from_mapping({
            "lead_id": "inbound-controlled-1",
            "contact": "Controlled Prospect",
            "company": "Controlled Company",
            "email": "prospect@controlled.test",
            "source": "Website",
            "selected_service": "fieldwork",
            "business_challenge": "Growth has slowed despite continued marketing investment.",
        })

        self.assertEqual(lead.selected_service, "FIELDWORK")
        self.assertEqual(
            lead.business_challenge,
            "Growth has slowed despite continued marketing investment.",
        )
        self.assertIn("DISCOVERY", lead.recommended_next_action)
        self.assertNotIn("Blueprint Lite", lead.recommended_next_action)
        self.assertFalse(lead.should_prepare_groundwork())
        self.assertEqual(lead.briefing_classification(), "legitimate_inbound_enquiry")

    def test_new_challenge_field_cannot_hide_test_or_spam_markers(self):
        base = {
            "contact": "Controlled Prospect",
            "company": "Controlled Company",
            "email": "prospect@controlled.test",
            "source": "Website",
            "selected_service": "FIELDWORK",
        }
        rehearsal = InboundLead.from_mapping({
            **base,
            "lead_id": "rehearsal-1",
            "business_challenge": "SAFE TEST ONLY — do not contact",
        })
        spam = InboundLead.from_mapping({
            **base,
            "lead_id": "spam-1",
            "business_challenge": "We sell SEO services and backlinks",
        })

        self.assertEqual(rehearsal.briefing_classification(), "test_or_rehearsal")
        self.assertEqual(spam.briefing_classification(), "suspicious_or_unverified")


if __name__ == "__main__":
    unittest.main()
