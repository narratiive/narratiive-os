from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_post_discovery_commercial import TonyPostDiscoveryCommercialCommandService


class DiscoveryReviewStub:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("discovery_outcome", "healthy", "Verified discovery review ready.", {
            "execution_status": "discovery_outcome_review_ready",
            "discovery_outcome": {
                "calendar_event_id": "event-1", "lead_id": "lead-1", "contact": "Alex", "company": "Example Co",
                "meeting_evidence": {"transcript_id": "t-1", "source_id": "fireflies:transcript:t-1", "summary": "Alex asked for a concrete proposal."},
                "review_evidence": {
                    "summary": "Strong buying signal and clear proposal request.",
                    "recommendation": "Prepare a concise proposal for Matt review.",
                    "objections": ["Budget is not yet confirmed."],
                    "agreed_actions": ["Send a proposal within the week."],
                    "evidence_gaps": ["Final decision timing is unknown."],
                },
                "recommended_next_action": "Prepare a concise proposal for Matt review.",
            }, "external_action_taken": False,
        })


class FakeGroundworkStore:
    def __init__(self, records=None):
        self._records = dict(records or {})

    def get(self, lead_id):
        return self._records.get(lead_id)

    def put(self, lead_id, record):
        self._records[lead_id] = dict(record)


def _completed_groundwork_record():
    return {
        "canonical_run_id": "lead-1-run",
        "state": "awaiting_review",
        "versions": [
            {
                "version": 1,
                "diagnostic_input_package": {"challenge": "Growth depends on accidental discovery."},
                "evidence": {
                    "growth_tension": "Example Co's growth depends on inconsistent word of mouth rather than a repeatable channel.",
                    "provisional_opportunity": "A focused positioning and acquisition system could make growth repeatable.",
                    "evidence_gaps": ["No verified paid-media history was found."],
                    "source_backed_evidence": [{"source_id": "web:example.com/about", "location": "https://example.com/about"}],
                    "fact_interpretation_hypothesis_lineage": {
                        "fact": "Example Co has grown primarily through referrals.",
                        "interpretation": "Growth is not yet driven by a repeatable acquisition system.",
                        "hypothesis": "A clearer positioning and one paid channel could compound referrals.",
                    },
                },
            }
        ],
    }


class TonyPostDiscoveryCommercialTests(unittest.TestCase):
    def test_positive_review_requires_approval_then_produces_commission_brief_without_dispatching_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            groundwork = FakeGroundworkStore({"lead-1": _completed_groundwork_record()})
            service = TonyPostDiscoveryCommercialCommandService(DiscoveryReviewStub(), {}, store_path=Path(tmp) / "state.json", groundwork_store=groundwork)
            routed = service.execute("check discovery", ())
            self.assertEqual(routed.data["execution_status"], "post_discovery_proposal_approval_required")
            self.assertIn("Say 'do that'", routed.message)

            prepared = service.execute("do that", ())

            self.assertEqual(prepared.data["execution_status"], "proposal_brief_ready")
            self.assertFalse(prepared.data["external_action_taken"])
            self.assertTrue(prepared.data["approval_required_for_external_proposal"])
            brief = prepared.data["proposal_commission_brief"]
            self.assertIn("Example Co", brief["copyable_commission"])
            self.assertIn("repeatable channel", brief["copyable_commission"])
            self.assertIn("Strong buying signal and clear proposal request", brief["sections"]["what_was_learned_in_discovery"])
            self.assertIn("Budget is not yet confirmed.", brief["sections"]["objections_and_risks"])
            self.assertTrue(any("groundwork_artefact" in src["kind"] for src in brief["sections"]["sources_and_lineage"]))
            self.assertTrue(any("fireflies:transcript:t-1" == src["source_id"] for src in brief["sections"]["sources_and_lineage"]))
            self.assertNotIn("I sent", brief["copyable_commission"])

    def test_no_fit_review_never_prepares_or_changes_state(self):
        class NoFitStub(DiscoveryReviewStub):
            def execute(self, command, objects):
                response = super().execute(command, objects)
                response.data["discovery_outcome"]["review_evidence"] = {"summary": "No fit at present.", "recommendation": "Nurture and stop active proposal work."}
                response.data["discovery_outcome"]["recommended_next_action"] = "Nurture and stop active proposal work."
                return response
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyPostDiscoveryCommercialCommandService(NoFitStub(), {}, store_path=Path(tmp) / "state.json")
            result = service.execute("check discovery", ())
            self.assertEqual(result.data["execution_status"], "post_discovery_no_proposal_recommended")
            self.assertFalse(result.data["post_discovery_commercial"]["write_actions_allowed"])

    def test_missing_groundwork_fails_closed_with_registration_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            groundwork = FakeGroundworkStore({})
            service = TonyPostDiscoveryCommercialCommandService(DiscoveryReviewStub(), {}, store_path=Path(tmp) / "state.json", groundwork_store=groundwork)
            service.execute("check discovery", ())

            response = service.execute("do that", ())

            self.assertEqual(response.data["execution_status"], "proposal_brief_requires_groundwork_registration")
            self.assertFalse(response.data["external_action_taken"])
            self.assertIn("governed manual Groundwork registration path", response.message)
            # The approval is retained, not invented away, so a later registration can be retried.
            self.assertIsNotNone(service.state["pending"])

    def test_manually_registered_groundwork_is_used_but_flagged_as_unapproved(self):
        with tempfile.TemporaryDirectory() as tmp:
            groundwork = FakeGroundworkStore({})
            service = TonyPostDiscoveryCommercialCommandService(DiscoveryReviewStub(), {}, store_path=Path(tmp) / "state.json", groundwork_store=groundwork)

            registration = service.register_manual_groundwork(
                "lead-1",
                content="Example Co's referral growth is not yet repeatable; a focused channel could change that.",
                producer="Matt",
                registered_by="Matt",
                rationale="Produced outside the system before this workflow existed; registering as an explicit exception.",
            )
            self.assertEqual(registration.data["execution_status"], "groundwork_manually_registered")
            self.assertEqual(registration.data["groundwork_registration"]["approval_status"], "not_accepted_on_registration")

            service.execute("check discovery", ())
            prepared = service.execute("do that", ())

            self.assertEqual(prepared.data["execution_status"], "proposal_brief_ready")
            brief = prepared.data["proposal_commission_brief"]
            self.assertIn("Manually registered by Matt", brief["sections"]["groundwork_provenance"])
            self.assertIn("not_accepted_on_registration", brief["sections"]["groundwork_provenance"])
            self.assertIn("Example Co's referral growth is not yet repeatable", brief["copyable_commission"])

    def test_registering_manual_groundwork_requires_exact_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            groundwork = FakeGroundworkStore({})
            service = TonyPostDiscoveryCommercialCommandService(DiscoveryReviewStub(), {}, store_path=Path(tmp) / "state.json", groundwork_store=groundwork)

            response = service.register_manual_groundwork("lead-1", content="", producer="Matt", registered_by="Matt", rationale="Reason")

            self.assertEqual(response.data["execution_status"], "groundwork_registration_requires_exact_fields")
            self.assertIsNone(groundwork.get("lead-1"))

    def test_groundwork_record_without_completed_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            groundwork = FakeGroundworkStore({"lead-1": {"canonical_run_id": "lead-1-run", "versions": []}})
            service = TonyPostDiscoveryCommercialCommandService(DiscoveryReviewStub(), {}, store_path=Path(tmp) / "state.json", groundwork_store=groundwork)
            service.execute("check discovery", ())

            response = service.execute("do that", ())

            self.assertEqual(response.data["execution_status"], "proposal_brief_requires_groundwork_registration")
            self.assertIn("no completed, quality-passed version", response.message)


if __name__ == "__main__":
    unittest.main()
