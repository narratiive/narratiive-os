from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_blueprint_client_delivery import TonyBlueprintClientDeliveryCommandService
from runtime.tony_command_service import CommandResponse


class Base:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("delivery_blueprint_persistence", "healthy", "Persisted.", {"execution_status": "delivery_blueprint_persisted_verified", "delivery_blueprint": {"delivery_project_record_id": "delivery-1", "lead_id": "lead-1", "contact": "Alex", "company": "Acme", "growth_blueprint_file_id": "file-1", "growth_blueprint_file_url": "https://drive.google.com/file-1", "growth_blueprint_filename": "Growth Blueprint - Acme.md"}})


class TonyBlueprintClientDeliveryTests(unittest.TestCase):
    def test_persisted_blueprint_requires_separate_delivery_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintClientDeliveryCommandService(Base(), store_path=Path(tmp)/"state.json")
            response = service.execute("status", ())
        self.assertEqual(response.data["execution_status"], "blueprint_client_delivery_approval_required")
        self.assertFalse(response.data["external_action_taken"])

    def test_generic_approval_does_not_share(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            service=TonyBlueprintClientDeliveryCommandService(Base(), {"Google Drive": lambda d: calls.append(d) or {}}, store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response=service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "blueprint_client_delivery_approval_required")
        self.assertEqual(calls, [])

    def test_scoped_approval_requires_exact_file_delivery_evidence(self):
        calls=[]
        def drive(dispatch):
            calls.append(dispatch)
            return {"verified": True, "mutation_count": 1, "file_id": "file-1", "share_url": "https://drive.google.com/shared/file-1", "shared": True}
        with tempfile.TemporaryDirectory() as tmp:
            service=TonyBlueprintClientDeliveryCommandService(Base(), {"Google Drive": drive}, store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response=service.execute("deliver Growth Blueprint", ())
        self.assertEqual(response.data["execution_status"], "blueprint_client_delivery_verified")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(calls[0]["payload"]["file_id"], "file-1")
        self.assertIn("not inferred", response.message.casefold())

    def test_wrong_file_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=TonyBlueprintClientDeliveryCommandService(Base(), {"Google Drive": lambda d: {"verified": True, "mutation_count": 1, "file_id": "other", "share_url": "https://x", "shared": True}}, store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response=service.execute("deliver Growth Blueprint", ())
        self.assertEqual(response.data["execution_status"], "blueprint_client_delivery_unverified")
        self.assertFalse(response.data["external_action_taken"])

    def test_missing_dispatcher_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=TonyBlueprintClientDeliveryCommandService(Base(), store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response=service.execute("deliver Growth Blueprint", ())
        self.assertEqual(response.data["execution_status"], "blueprint_client_delivery_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__": unittest.main()
