from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_delivery_blueprint_review import TonyDeliveryBlueprintReviewCommandService


class _BaseService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return _commissioned_response()


def _commissioned_response():
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
                "work_product": {
                    "work_product": "Internal delivery kickoff package",
                    "known_facts": ["Client is onboarded", "Delivery workspace is verified"],
                    "evidence_gaps": ["Primary audience still requires client validation"],
                    "research_plan": ["Review verified client materials", "Validate market and audience evidence"],
                    "workplan": ["Strategy", "Research", "Creative", "Client Deliverables", "Reporting"],
                },
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


class TonyApprovedBlueprintDrivePersistenceTests(unittest.TestCase):
    def _ready_service(self, tmp, drive=None):
        dispatchers = {"Claude": lambda dispatch: _blueprint_evidence()}
        if drive is not None:
            dispatchers["Google Drive"] = drive
        service = TonyDeliveryBlueprintReviewCommandService(
            _BaseService(),
            dispatchers,
            store_path=Path(tmp) / "state.json",
        )
        ready = service.execute("continue delivery", ())
        self.assertEqual(ready.data["execution_status"], "delivery_blueprint_ready_for_approval")
        return service

    def test_generic_approval_does_not_write_client_artifact(self):
        drive_calls = []
        with tempfile.TemporaryDirectory() as tmp:
            service = self._ready_service(tmp, lambda dispatch: drive_calls.append(dispatch) or {})
            response = service.execute("do that", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_persistence_approval_required")
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(drive_calls, [])
        self.assertIn("generic approval is not enough", response.message)

    def test_scoped_approval_persists_exact_reviewed_blueprint_to_verified_drive_folder(self):
        calls = []

        def drive(dispatch):
            calls.append(dispatch)
            return {
                "verified": True,
                "created": True,
                "mutation_count": 1,
                "file_id": "blueprint-file-1",
                "url": "https://drive.google.com/file/d/blueprint-file-1/view",
            }

        with tempfile.TemporaryDirectory() as tmp:
            service = self._ready_service(tmp, drive)
            response = service.execute("approve Growth Blueprint", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_persisted_verified")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(len(calls), 1)
        dispatch = calls[0]
        self.assertEqual(dispatch["execution_mode"], "approval_gated_write")
        self.assertTrue(dispatch["approval_granted"])
        self.assertEqual(dispatch["approval_scope"], "reviewed_growth_blueprint_to_verified_client_workspace")
        self.assertEqual(dispatch["payload"]["parent_folder_id"], "folder-1")
        self.assertEqual(dispatch["payload"]["folder"], "01 Strategy")
        self.assertIn("Growth Blueprint - Example Co.md", dispatch["payload"]["filename"])
        self.assertIn("unresolved audience", str(dispatch["payload"]["content"]).casefold())
        self.assertIn("Do not share the file externally", dispatch["instruction"])
        self.assertEqual(response.data["delivery_blueprint"]["growth_blueprint_file_id"], "blueprint-file-1")

    def test_missing_drive_dispatcher_fails_closed_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._ready_service(tmp)
            response = service.execute("approve Growth Blueprint", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_drive_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("not written", response.message)

    def test_unverified_drive_evidence_does_not_mark_blueprint_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._ready_service(
                tmp,
                lambda dispatch: {"verified": True, "created": True, "mutation_count": 1, "file_id": "file-without-url"},
            )
            response = service.execute("approve Growth Blueprint", ())

        self.assertEqual(response.data["execution_status"], "delivery_blueprint_drive_write_unverified")
        self.assertFalse(response.data["external_action_taken"])

    def test_verified_persistence_is_replay_safe_across_restart(self):
        calls = []

        def drive(dispatch):
            calls.append(dispatch)
            return {"verified": True, "created": True, "mutation_count": 1, "file_id": "file-1", "url": "https://drive.google.com/file-1"}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            first = TonyDeliveryBlueprintReviewCommandService(_BaseService(), {"Claude": lambda dispatch: _blueprint_evidence(), "Google Drive": drive}, store_path=path)
            first.execute("continue delivery", ())
            first.execute("approve Growth Blueprint", ())
            second = TonyDeliveryBlueprintReviewCommandService(_BaseService(), {"Claude": lambda dispatch: _blueprint_evidence(), "Google Drive": drive}, store_path=path)
            response = second.execute("approve Growth Blueprint", ())

        self.assertEqual(len(calls), 1)
        self.assertEqual(response.data["execution_status"], "delivery_commission_verified")


if __name__ == "__main__":
    unittest.main()
