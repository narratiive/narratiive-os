from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_delivery_blueprint_review import TonyDeliveryBlueprintReviewCommandService


class _BaseService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response

    def execute(self, command, objects):
        return self.response


def _commissioned_response(*, kickoff=None):
    evidence = kickoff or {
        "work_product": "Internal delivery kickoff package",
        "known_facts": ["Client is onboarded", "Delivery workspace is verified"],
        "evidence_gaps": ["Primary audience still requires client validation"],
        "research_plan": ["Review verified client materials", "Validate market and audience evidence"],
        "workplan": ["Strategy", "Research", "Creative", "Client Deliverables", "Reporting"],
    }
    return CommandResponse(
        "delivery_commissioning",
        "healthy",
        "Kickoff returned.",
        {
            "execution_status": "delivery_commission_verified",
            "delivery_commissioning": {
                "delivery_project_record_id": "delivery-1",
                "drive_folder_id": "folder-1",
                "drive_folder_url": "https://drive.google.com/folder-1",
                "onboarding_record_id": "onboard-1",
                "lead_id": "lead-1",
                "contact": "Alex Example",
                "company": "Example Co",
                "work_product": evidence,
            },
            "external_action_taken": False,
        },
    )


def _blueprint_evidence():
    blueprint = " ".join(
        [
            "This internal Growth Blueprint frames the verified client situation, evidence boundaries, strategic challenge,",
            "market context, audience uncertainty, positioning opportunity, growth hypothesis, research priorities, creative implications,",
            "measurement approach and next decisions. It keeps unresolved audience and category questions explicit rather than",
            "turning them into facts, and it is intentionally a working draft for Tony review before any client-facing delivery.",
        ]
    )
    return {
        "work_product": blueprint,
        "growth_blueprint": blueprint,
        "sources": ["verified onboarding record", "verified delivery kickoff evidence"],
        "evidence_gaps": ["Primary audience needs client validation"],
        "narratiive_fit": "Strong fit for a clarity-led Growth Blueprint engagement.",
        "strategic_growth_opportunity": "Clarify the highest-value market and audience opportunity before creative development.",
        "recommendation": "Advance to Matt approval after Tony review.",
    }


class TonyDeliveryBlueprintReviewTests(unittest.TestCase):
    def test_reviews_kickoff_and_prepares_blueprint_autonomously(self):
        calls = []

        def claude(dispatch):
            calls.append(dispatch)
            return _blueprint_evidence()

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBlueprintReviewCommandService(
                _BaseService(_commissioned_response()),
                {"Claude": claude},
                store_path=Path(tmp) / "state.json",
            )
            response = service.execute("anything", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_ready_for_approval")
        self.assertTrue(response.data["approval_required"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["execution_mode"], "autonomous_prepare")
        self.assertEqual(calls[0]["target"]["workspace_access"], "reference_only")
        self.assertIn("Do not write to Google Drive or Notion", calls[0]["instruction"])
        self.assertEqual(response.data["tony_review"]["status"], "ready_for_approval")

    def test_fails_closed_when_kickoff_is_missing_decision_grade_components(self):
        kickoff = {
            "work_product": "Thin kickoff",
            "known_facts": ["Client onboarded"],
            "evidence_gaps": ["Audience unknown"],
        }
        called = []
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBlueprintReviewCommandService(
                _BaseService(_commissioned_response(kickoff=kickoff)),
                {"Claude": lambda dispatch: called.append(dispatch) or _blueprint_evidence()},
                store_path=Path(tmp) / "state.json",
            )
            response = service.execute("anything", ())

        self.assertEqual(response.data["execution_status"], "delivery_kickoff_revision_required")
        self.assertEqual(called, [])
        self.assertIn("research_plan", response.data["delivery_blueprint"]["kickoff_review"]["failed_checks"])
        self.assertIn("workplan", response.data["delivery_blueprint"]["kickoff_review"]["failed_checks"])

    def test_no_live_claude_does_not_claim_blueprint_prepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBlueprintReviewCommandService(
                _BaseService(_commissioned_response()),
                {},
                store_path=Path(tmp) / "state.json",
            )
            response = service.execute("anything", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_dispatcher_unavailable")
        self.assertFalse(response.data["delivery_blueprint"]["blueprint_prepared"])
        self.assertFalse(response.data["external_action_taken"])

    def test_tony_quality_gate_blocks_weak_blueprint(self):
        weak = {
            "work_product": "Too short",
            "growth_blueprint": "Too short",
            "sources": ["verified kickoff"],
            "evidence_gaps": ["Audience unknown"],
            "narratiive_fit": "Fit exists",
            "strategic_growth_opportunity": "Opportunity exists",
            "recommendation": "Advance",
        }
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryBlueprintReviewCommandService(
                _BaseService(_commissioned_response()),
                {"Claude": lambda dispatch: weak},
                store_path=Path(tmp) / "state.json",
            )
            response = service.execute("anything", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_revision_required")
        self.assertFalse(response.data["approval_required"])
        self.assertIn("blueprint_present", response.data["tony_review"]["failed_checks"])

    def test_replay_is_suppressed_after_ready_blueprint(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            first = TonyDeliveryBlueprintReviewCommandService(
                _BaseService(_commissioned_response()),
                {"Claude": lambda dispatch: calls.append(dispatch) or _blueprint_evidence()},
                store_path=path,
            )
            first.execute("anything", ())
            second = TonyDeliveryBlueprintReviewCommandService(
                _BaseService(_commissioned_response()),
                {"Claude": lambda dispatch: calls.append(dispatch) or _blueprint_evidence()},
                store_path=path,
            )
            response = second.execute("anything", ())

        self.assertEqual(len(calls), 1)
        self.assertEqual(response.data["execution_status"], "delivery_commission_verified")


if __name__ == "__main__":
    unittest.main()
