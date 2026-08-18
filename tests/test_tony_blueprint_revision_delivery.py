from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_blueprint_revision_delivery import TonyBlueprintRevisionDeliveryCommandService
from runtime.tony_command_service import CommandResponse


class Base:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse(
            "blueprint_revision_persistence", "healthy", "Revision persisted.",
            {"execution_status": "blueprint_revision_persisted_verified", "blueprint_revision": {
                "delivery_project_record_id": "delivery-1", "lead_id": "lead-1", "contact": "Alex", "company": "Acme",
                "growth_blueprint_file_id": "file-original", "original_delivered_file_id": "file-original",
                "revision_file_id": "file-revision", "revision_file_url": "https://drive.google.com/file-revision",
                "feedback_message_id": "msg-1",
            }},
        )


class TonyBlueprintRevisionDeliveryTests(unittest.TestCase):
    def test_persisted_revision_requires_fresh_redelivery_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionDeliveryCommandService(Base(), store_path=Path(tmp)/"state.json")
            response = service.execute("status", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_approval_required")
        self.assertFalse(response.data["external_action_taken"])

    def test_generic_approval_does_not_redeliver(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionDeliveryCommandService(Base(), {"Google Drive": lambda d: calls.append(d) or {}}, store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response = service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_approval_required")
        self.assertEqual(calls, [])

    def test_scoped_approval_redelivers_exact_revision_only(self):
        calls=[]
        def drive(dispatch):
            calls.append(dispatch)
            return {"verified": True, "mutation_count": 1, "file_id": "file-revision", "share_url": "https://drive.google.com/shared/file-revision", "shared": True}
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionDeliveryCommandService(Base(), {"Google Drive": drive}, store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response = service.execute("redeliver Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_verified")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(calls[0]["payload"]["revision_file_id"], "file-revision")
        self.assertEqual(calls[0]["payload"]["original_delivered_file_id"], "file-original")
        self.assertIn("untouched", response.message.casefold())

    def test_wrong_file_delivery_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionDeliveryCommandService(Base(), {"Google Drive": lambda d: {"verified": True, "mutation_count": 1, "file_id": "file-original", "share_url": "https://x", "shared": True}}, store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response = service.execute("deliver Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_unverified")
        self.assertFalse(response.data["external_action_taken"])

    def test_missing_dispatcher_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionDeliveryCommandService(Base(), store_path=Path(tmp)/"state.json")
            service.execute("status", ())
            response = service.execute("redeliver Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__": unittest.main()
