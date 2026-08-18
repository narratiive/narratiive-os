from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_blueprint_revision_persistence import TonyBlueprintRevisionPersistenceCommandService
from runtime.tony_command_service import CommandResponse


class _Base:
    mission_control_loader = None
    github_configured = False
    def execute(self, command, objects):
        return CommandResponse("revision", "healthy", "Revision ready.", {"execution_status": "blueprint_revision_ready_for_approval", "blueprint_revision": {"delivery_project_record_id": "delivery-1", "growth_blueprint_file_id": "delivered-1", "feedback_message_id": "msg-1", "company": "Example Co", "revision": {"growth_blueprint": "Revised grounded Blueprint", "sources": ["verified source"], "evidence_gaps": ["gap"]}, "tony_review": {"status": "ready_for_approval"}}, "external_action_taken": False})


class TonyBlueprintRevisionPersistenceTests(unittest.TestCase):
    def _service(self, tmp, drive=None):
        dispatchers = {} if drive is None else {"Google Drive": drive}
        return TonyBlueprintRevisionPersistenceCommandService(_Base(), dispatchers, store_path=Path(tmp) / "state.json")

    def test_generic_approval_does_not_write_revision(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            service=self._service(tmp, lambda d: calls.append(d) or {})
            ready=service.execute("revision status", ())
            response=service.execute("do that", ())
        self.assertEqual(ready.data["execution_status"], "blueprint_revision_persistence_approval_required")
        self.assertEqual(response.data["execution_status"], "blueprint_revision_persistence_approval_required")
        self.assertEqual(calls, [])

    def test_scoped_approval_creates_distinct_revision_without_overwrite(self):
        calls=[]
        def drive(dispatch):
            calls.append(dispatch); return {"verified": True, "created": True, "mutation_count": 1, "file_id": "revision-2", "url": "https://drive.google.com/revision-2"}
        with tempfile.TemporaryDirectory() as tmp:
            service=self._service(tmp, drive); service.execute("revision status", ()); response=service.execute("approve Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_persisted_verified")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(calls[0]["payload"]["original_delivered_file_id"], "delivered-1")
        self.assertIn("Do not overwrite", calls[0]["instruction"])
        self.assertEqual(response.data["blueprint_revision"]["revision_file_id"], "revision-2")
        self.assertIn("separate client-redelivery approval", response.message)

    def test_same_file_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=self._service(tmp, lambda d: {"verified": True, "created": True, "mutation_count": 1, "file_id": "delivered-1", "url": "https://drive.google.com/delivered-1"}); service.execute("revision status", ()); response=service.execute("approve blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_drive_write_unverified")
        self.assertFalse(response.data["external_action_taken"])

    def test_missing_drive_dispatcher_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=self._service(tmp); service.execute("revision status", ()); response=service.execute("approve blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_drive_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__": unittest.main()
