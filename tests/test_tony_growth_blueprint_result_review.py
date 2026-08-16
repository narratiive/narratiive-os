from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("agency_focus_action", "healthy", "Growth Blueprint preparation ready.", {"execution_handoff": {"worker": "Claude", "approval_required": False, "execution_truth": "handoff_prepared_only", "dispatch": {"eligible": True, "state": "ready_for_autonomous_dispatch", "worker": "Claude", "instruction": "Research this inbound lead and prepare an evidence-grounded Growth Blueprint. Do not prepare or send outreach.", "target": {"lead_id": "lead-1", "contact": "Alex Example", "area": "commercial"}, "execution_mode": "autonomous_prepare", "expected_evidence": "Growth Blueprint evidence package", "return_to": "Tony", "execution_truth": "not_dispatched"}}})


class TonyGrowthBlueprintResultReviewTests(unittest.TestCase):
    def service(self, evidence):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        return TonyCommercialAutonomousJudgementCommandService(StubCommandService(), dispatchers={"Claude": lambda contract: evidence}, store_path=Path(tmp.name) / "result.json")

    def strong_evidence(self):
        return {"growth_blueprint": " ".join(["Example Co has a clear but underdeveloped growth opportunity requiring sharper positioning and a stronger commercial narrative."] * 6), "sources": ["https://example.com/about", "https://example.com/news"], "evidence_gaps": ["Conversion data is not public."], "narratiive_fit": "Strong strategic clarity and growth-system fit.", "strategic_growth_opportunity": "Unify positioning and demand generation around one defensible growth narrative.", "recommendation": "Advance to Matt approval."}

    def test_verified_blueprint_is_automatically_reviewed_and_presented_for_approval(self):
        response = self.service(self.strong_evidence()).execute("OK, do that", [])
        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "growth_blueprint_ready")
        self.assertEqual(judgement["review_status"], "ready_for_approval")
        self.assertTrue(all(judgement["review_checks"].values()))
        self.assertEqual(judgement["execution_next_action"], "")
        self.assertIn("ready for your approval", response.message)
        self.assertIn("Nothing has been sent externally", response.message)

    def test_incomplete_blueprint_is_returned_for_autonomous_revision_not_outreach(self):
        evidence = self.strong_evidence(); evidence.pop("sources")
        response = self.service(evidence).execute("OK, do that", [])
        judgement = response.data["commercial_judgement"]
        self.assertEqual(judgement["disposition"], "growth_blueprint_revision_required")
        self.assertIn("source_backed_evidence_present", judgement["failed_checks"])
        self.assertIn("Revise the Growth Blueprint", judgement["execution_next_action"])
        self.assertNotIn("send outreach", judgement["execution_next_action"].casefold())
        self.assertIn("would not progress it yet", response.message)


if __name__ == "__main__": unittest.main()
