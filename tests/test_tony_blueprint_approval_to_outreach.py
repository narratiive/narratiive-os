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
        return CommandResponse(
            "agency_focus_action", "healthy", "Growth Blueprint preparation ready.",
            {"execution_handoff": {"worker": "Claude", "approval_required": False, "dispatch": {"eligible": True, "state": "ready_for_autonomous_dispatch", "worker": "Claude", "instruction": "Research this lead and prepare an evidence-grounded Growth Blueprint. Do not prepare or send outreach.", "target": {"lead_id": "lead-1", "contact": "Alex Example", "area": "commercial"}, "execution_mode": "autonomous_prepare", "expected_evidence": "Growth Blueprint evidence package", "return_to": "Tony", "execution_truth": "not_dispatched"}}},
        )


class TonyBlueprintApprovalToOutreachTests(unittest.TestCase):
    def test_approved_reviewed_blueprint_progresses_to_draft_only_outreach_preparation(self):
        blueprint_evidence = {
            "growth_blueprint": " ".join(["Example Co has a clear growth opportunity requiring sharper positioning and a stronger commercial narrative."] * 7),
            "sources": ["https://example.com/about", "https://example.com/news"],
            "evidence_gaps": ["Conversion data is not public."],
            "narratiive_fit": "Strong strategic clarity and growth-system fit.",
            "strategic_growth_opportunity": "Unify positioning and demand generation around one defensible growth narrative.",
            "recommendation": "Advance to Matt approval.",
        }
        outreach_evidence = {
            "email_subject": "A sharper growth story for Example Co",
            "email_body": (
                "Hi Alex, I have been looking at how Example Co is presenting its growth story and there is a strong opportunity "
                "to make the proposition easier to understand, remember and choose. The evidence suggests the business has real "
                "momentum, but the positioning and demand story could work harder together. Narratiive helps businesses turn that "
                "kind of strategic clarity into a stronger commercial narrative and a more coherent route to growth. If useful, "
                "I would be happy to compare notes and show you the opportunity we can see."
            ),
        }
        calls = []

        def claude(contract):
            calls.append(contract)
            instruction = str(contract.get("instruction") or "").casefold()
            if "tailored outreach package" in instruction:
                return outreach_evidence
            return blueprint_evidence

        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        service = TonyCommercialAutonomousJudgementCommandService(StubCommandService(), dispatchers={"Claude": claude}, store_path=Path(tmp.name) / "result.json")

        reviewed = service.execute("OK, do that", [])
        self.assertEqual(reviewed.data["commercial_judgement"]["disposition"], "growth_blueprint_ready")
        self.assertIn("ready for your approval", reviewed.message)
        self.assertIn("Nothing has been sent externally", reviewed.message)

        approved = service.execute("OK, do that", [])
        handoff = approved.data["execution_handoff"]
        self.assertEqual(handoff["worker"], "Claude")
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["dispatch"]["state"], "dispatch_verified")
        self.assertEqual(handoff["dispatch"]["execution_truth"], "verified_dispatch")
        self.assertEqual(approved.data["execution_status"], "autonomous_step_verified")
        self.assertEqual(approved.data["dispatch_result"]["worker"], "Claude")
        self.assertEqual(approved.data["commercial_judgement"]["disposition"], "outreach_package_ready")
        self.assertIn("tailored outreach package", handoff["action"])
        self.assertIn("reviewed Growth Blueprint", handoff["dispatch"]["instruction"])
        self.assertIn("Do not send the email", handoff["dispatch"]["instruction"])
        self.assertIn("do not invent claims", handoff["dispatch"]["instruction"].casefold())
        self.assertEqual(len(calls), 2)
        self.assertFalse(approved.data["external_action_taken"])


if __name__ == "__main__": unittest.main()
