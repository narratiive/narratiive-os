from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_drive_delivery_workspace import TonyDriveDeliveryWorkspaceCommandService


class StubService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse):
        self.response = response

    def execute(self, command, objects):
        return self.response


def delivery_response():
    return CommandResponse(
        "delivery_bootstrap",
        "healthy",
        "Delivery bootstrap verified.",
        {"execution_status": "delivery_bootstrap_verified", "delivery_bootstrap": {"delivery_project_record_id": "delivery-1", "onboarding_record_id": "onb-1", "lead_id": "lead-1", "contact": "Alex", "company": "Acme", "workspace_created": True}},
    )


class TonyDriveDeliveryWorkspaceTests(unittest.TestCase):
    def test_verified_delivery_requires_separate_drive_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDriveDeliveryWorkspaceCommandService(StubService(delivery_response()), store_path=Path(tmp) / "drive.json")
            response = service.execute("status", [])
            self.assertEqual(response.data["execution_status"], "drive_workspace_approval_required")
            self.assertFalse(response.data["drive_workspace"]["workspace_created"])
            self.assertFalse(response.data["external_action_taken"])

    def test_generic_approval_does_not_create_drive_workspace(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDriveDeliveryWorkspaceCommandService(StubService(delivery_response()), dispatchers={"Google Drive": lambda dispatch: calls.append(dispatch)}, store_path=Path(tmp) / "drive.json")
            service.execute("status", [])
            response = service.execute("do that", [])
            self.assertEqual(response.data["execution_status"], "drive_workspace_approval_required")
            self.assertEqual(calls, [])

    def test_scoped_approval_requires_verified_drive_evidence(self):
        captured = []
        def drive(dispatch):
            captured.append(dispatch)
            return {"verified": True, "mutation_count": 6, "folder_id": "folder-1", "folder_url": "https://drive.google.com/drive/folders/folder-1"}
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDriveDeliveryWorkspaceCommandService(StubService(delivery_response()), dispatchers={"Google Drive": drive}, store_path=Path(tmp) / "drive.json")
            service.execute("status", [])
            response = service.execute("create Drive workspace", [])
            self.assertEqual(response.data["execution_status"], "drive_workspace_verified")
            self.assertEqual(response.data["drive_workspace"]["drive_folder_id"], "folder-1")
            self.assertTrue(response.data["external_action_taken"])
            self.assertEqual(captured[0]["execution_mode"], "approval_gated_write")
            self.assertFalse(captured[0].get("share_externally", False))

    def test_missing_drive_dispatcher_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDriveDeliveryWorkspaceCommandService(StubService(delivery_response()), store_path=Path(tmp) / "drive.json")
            service.execute("status", [])
            response = service.execute("create Drive workspace", [])
            self.assertEqual(response.data["execution_status"], "drive_workspace_dispatcher_unavailable")
            self.assertFalse(response.data["external_action_taken"])

    def test_unverified_drive_evidence_does_not_create_workspace(self):
        def drive(dispatch):
            return {"verified": True, "mutation_count": 1, "folder_id": "folder-1"}
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyDriveDeliveryWorkspaceCommandService(StubService(delivery_response()), dispatchers={"Google Drive": drive}, store_path=Path(tmp) / "drive.json")
            service.execute("status", [])
            response = service.execute("create Drive workspace", [])
            self.assertEqual(response.data["execution_status"], "drive_workspace_write_unverified")
            self.assertFalse(response.data["external_action_taken"])

    def test_pending_state_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drive.json"
            first = TonyDriveDeliveryWorkspaceCommandService(StubService(delivery_response()), store_path=path)
            first.execute("status", [])
            second = TonyDriveDeliveryWorkspaceCommandService(StubService(CommandResponse("status", "healthy", "ok", {})), store_path=path)
            response = second.execute("do that", [])
            self.assertEqual(response.data["drive_workspace"]["delivery_project_record_id"], "delivery-1")


if __name__ == "__main__":
    unittest.main()
