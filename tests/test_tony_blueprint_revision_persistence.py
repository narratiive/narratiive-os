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
    def _service(self, tmp, drive=None, notion=None):
        dispatchers = {}
        if drive is not None: dispatchers["Google Drive"] = drive
        if notion is not None: dispatchers["Notion"] = notion
        return TonyBlueprintRevisionPersistenceCommandService(_Base(), dispatchers, store_path=Path(tmp) / "state.json")

    @staticmethod
    def _drive(calls=None):
        def drive(dispatch):
            if calls is not None: calls.append(dispatch)
            if dispatch["payload"]["kind"] == "growth_blueprint_revision":
                return {"verified": True, "created": True, "mutation_count": 1, "file_id": "revision-2", "url": "https://drive.google.com/revision-2"}
            return {"verified": True, "mutation_count": 1, "file_id": "revision-2", "share_url": "https://drive.google.com/shared/revision-2", "shared": True}
        return drive

    def _persisted_service(self, tmp, drive):
        service = self._service(tmp, drive)
        service.execute("revision status", ())
        persisted = service.execute("approve Growth Blueprint revision", ())
        return service, persisted

    def _redelivered_service(self, tmp, drive=None, notion=None):
        service = self._service(tmp, drive or self._drive(), notion)
        service.execute("revision status", ())
        service.execute("approve Growth Blueprint revision", ())
        redelivered = service.execute("redeliver Growth Blueprint revision", ())
        return service, redelivered

    def test_generic_approval_does_not_write_revision(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            service=self._service(tmp, lambda d: calls.append(d) or {})
            ready=service.execute("revision status", ())
            response=service.execute("do that", ())
        self.assertEqual(ready.data["execution_status"], "blueprint_revision_persistence_approval_required")
        self.assertEqual(response.data["execution_status"], "blueprint_revision_persistence_approval_required")
        self.assertEqual(calls, [])

    def test_scoped_approval_creates_distinct_revision_then_requires_redelivery_approval(self):
        calls=[]
        def drive(dispatch):
            calls.append(dispatch); return {"verified": True, "created": True, "mutation_count": 1, "file_id": "revision-2", "url": "https://drive.google.com/revision-2"}
        with tempfile.TemporaryDirectory() as tmp:
            service=self._service(tmp, drive); service.execute("revision status", ()); response=service.execute("approve Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_approval_required")
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(calls[0]["payload"]["original_delivered_file_id"], "delivered-1")
        self.assertIn("Do not overwrite", calls[0]["instruction"])
        self.assertEqual(response.data["blueprint_revision"]["revision_file_id"], "revision-2")
        self.assertEqual(response.data["drive_revision_evidence"]["file_id"], "revision-2")
        self.assertIn("separate scoped approval", response.message)

    def test_generic_approval_after_persistence_does_not_redeliver(self):
        calls=[]
        def drive(dispatch):
            calls.append(dispatch)
            return {"verified": True, "created": True, "mutation_count": 1, "file_id": "revision-2", "url": "https://drive.google.com/revision-2"}
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._persisted_service(tmp, drive)
            response=service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_approval_required")
        self.assertEqual(len(calls), 1)

    def test_scoped_redelivery_shares_exact_revision_then_requires_notion_approval(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._persisted_service(tmp, self._drive(calls))
            response=service.execute("redeliver Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_approval_required")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(calls[1]["payload"]["revision_file_id"], "revision-2")
        self.assertEqual(calls[1]["payload"]["original_delivered_file_id"], "delivered-1")
        self.assertIn("previously delivered Blueprint remains untouched", response.message)
        self.assertIn("record Growth Blueprint revision delivery", response.message)

    def test_generic_approval_after_redelivery_does_not_mutate_notion(self):
        notion_calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._redelivered_service(tmp, notion=lambda d: notion_calls.append(d) or {})
            response=service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_approval_required")
        self.assertEqual(notion_calls, [])

    def test_scoped_notion_approval_records_exact_revision_delivery(self):
        notion_calls=[]
        def notion(dispatch):
            notion_calls.append(dispatch)
            return {"verified": True, "mutation_count": 1, "record_id": "delivery-1", "status": "Growth Blueprint revision delivered"}
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._redelivered_service(tmp, notion=notion)
            response=service.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_verified")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(response.data["notion_record_id"], "delivery-1")
        self.assertEqual(notion_calls[0]["payload"]["revision_file_id"], "revision-2")
        self.assertEqual(notion_calls[0]["payload"]["original_delivered_file_id"], "delivered-1")
        self.assertEqual(notion_calls[0]["approval_scope"], "verified_growth_blueprint_revision_delivery_state_sync")
        self.assertFalse("accept" in notion_calls[0]["instruction"].casefold() and "do not infer" not in notion_calls[0]["instruction"].casefold())

    def test_wrong_notion_status_does_not_become_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._redelivered_service(tmp, notion=lambda d: {"verified": True, "mutation_count": 1, "record_id": "delivery-1", "status": "Growth Blueprint delivered"})
            response=service.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_unverified")
        self.assertFalse(response.data["external_action_taken"])

    def test_missing_notion_dispatcher_fails_closed_after_redelivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._redelivered_service(tmp)
            response=service.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])

    def test_verified_notion_sync_is_replay_safe_across_restart(self):
        notion_calls=[]
        def notion(dispatch):
            notion_calls.append(dispatch)
            return {"verified": True, "mutation_count": 1, "record_id": "delivery-1", "status": "Growth Blueprint revision delivered"}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state.json"
            service=TonyBlueprintRevisionPersistenceCommandService(_Base(), {"Google Drive": self._drive(), "Notion": notion}, store_path=path)
            service.execute("revision status", ())
            service.execute("approve Growth Blueprint revision", ())
            service.execute("redeliver Growth Blueprint revision", ())
            service.execute("record Growth Blueprint revision delivery", ())
            restarted=TonyBlueprintRevisionPersistenceCommandService(_Base(), {"Google Drive": self._drive(), "Notion": notion}, store_path=path)
            response=restarted.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(len(notion_calls), 1)
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_verified")
        self.assertFalse(response.data["external_action_taken"])

    def test_wrong_file_redelivery_evidence_is_rejected(self):
        def drive(dispatch):
            if dispatch["payload"]["kind"] == "growth_blueprint_revision":
                return {"verified": True, "created": True, "mutation_count": 1, "file_id": "revision-2", "url": "https://drive.google.com/revision-2"}
            return {"verified": True, "mutation_count": 1, "file_id": "delivered-1", "share_url": "https://x", "shared": True}
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self._persisted_service(tmp, drive)
            response=service.execute("deliver Growth Blueprint revision", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_unverified")
        self.assertFalse(response.data["external_action_taken"])

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
