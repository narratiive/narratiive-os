from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_delivery_commissioning import TonyDeliveryCommissioningCommandService


class StubService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse):
        self.response = response

    def execute(self, command, objects):
        return self.response


def drive_response():
    return CommandResponse(
        "drive_delivery_workspace",
        "healthy",
        "Drive workspace verified.",
        {
            "execution_status": "drive_workspace_verified",
            "drive_workspace": {
                "delivery_project_record_id": "delivery-1",
                "onboarding_record_id": "onb-1",
                "lead_id": "lead-1",
                "contact": "Alex",
                "company": "Acme",
                "drive_folder_id": "folder-1",
                "drive_folder_url": "https://drive.google.com/drive/folders/folder-1",
                "workspace_created": True,
            },
        },
    )


class TonyDeliveryCommissioningTests(unittest.TestCase):
    def test_verified_workspace_autonomously_commissions_safe_claude_preparation(self):
        captured = []

        def claude(dispatch):
            captured.append(dispatch)
            return {
                "verified": True,
                "provider_message_id": "msg-1",
                "work_product": "A bounded delivery kickoff package.",
                "evidence_gaps": ["Client growth objective is not yet evidenced."],
                "recommendation": "Resolve evidence gaps before client-facing strategy work.",
            }

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryCommissioningCommandService(
                StubService(drive_response()),
                dispatchers={"Claude": claude},
                store_path=Path(tmp) / "commission.json",
            )
            response = service.execute("status", [])

        self.assertEqual(response.data["execution_status"], "delivery_commission_verified")
        self.assertTrue(response.data["delivery_commissioning"]["commissioned"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(captured[0]["execution_mode"], "autonomous_prepare")
        self.assertTrue(captured[0]["eligible"])
        self.assertEqual(captured[0]["target"]["drive_folder_id"], "folder-1")
        self.assertIn("Do not write to Google Drive", captured[0]["instruction"])

    def test_missing_claude_dispatcher_fails_closed_and_persists_pending_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commission.json"
            service = TonyDeliveryCommissioningCommandService(StubService(drive_response()), store_path=path)
            response = service.execute("status", [])
            restarted = TonyDeliveryCommissioningCommandService(
                StubService(CommandResponse("status", "healthy", "ok", {})),
                store_path=path,
            )

        self.assertEqual(response.data["execution_status"], "delivery_commission_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(restarted.state["pending"]["delivery_project_record_id"], "delivery-1")

    def test_unverified_claude_return_is_not_treated_as_commissioned(self):
        def claude(dispatch):
            return {"verified": False, "work_product": "draft", "evidence_gaps": []}

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryCommissioningCommandService(
                StubService(drive_response()),
                dispatchers={"Claude": claude},
                store_path=Path(tmp) / "commission.json",
            )
            response = service.execute("status", [])

        self.assertEqual(response.data["execution_status"], "delivery_commission_dispatch_unverified")
        self.assertFalse(response.data["delivery_commissioning"]["commissioned"])

    def test_return_without_explicit_evidence_gaps_fails_quality_gate(self):
        def claude(dispatch):
            return {"verified": True, "provider_message_id": "msg-1", "work_product": "draft"}

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDeliveryCommissioningCommandService(
                StubService(drive_response()),
                dispatchers={"Claude": claude},
                store_path=Path(tmp) / "commission.json",
            )
            response = service.execute("status", [])

        self.assertEqual(response.data["execution_status"], "delivery_commission_quality_gate_failed")
        self.assertFalse(response.data["delivery_commissioning"]["commissioned"])

    def test_verified_commission_is_not_replayed_for_same_delivery_project(self):
        calls = []

        def claude(dispatch):
            calls.append(dispatch)
            return {
                "verified": True,
                "provider_message_id": "msg-1",
                "work_product": "kickoff",
                "evidence_gaps": [],
            }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commission.json"
            service = TonyDeliveryCommissioningCommandService(
                StubService(drive_response()), dispatchers={"Claude": claude}, store_path=path
            )
            first = service.execute("status", [])
            second = service.execute("status", [])

        self.assertEqual(first.data["execution_status"], "delivery_commission_verified")
        self.assertEqual(second.command, "drive_delivery_workspace")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
