from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_blueprint_revision_notion_sync import TonyBlueprintRevisionNotionSyncCommandService
from runtime.tony_command_service import CommandResponse


class Base:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "blueprint_revision_persistence",
            "healthy",
            "Revision redelivery verified.",
            {
                "execution_status": "blueprint_revision_client_delivery_verified",
                "blueprint_revision_delivery": {
                    "delivery_project_record_id": "delivery-1",
                    "lead_id": "lead-1",
                    "contact": "Alex",
                    "company": "Acme",
                    "revision_file_id": "file-r2",
                    "revision_file_url": "https://drive.google.com/file-r2",
                    "original_delivered_file_id": "file-r1",
                    "delivery_url": "https://drive.google.com/shared/file-r2",
                    "feedback_message_id": "msg-feedback-1",
                    "state": "revision_client_delivery_verified",
                },
                "external_action_taken": True,
            },
        )


class TonyBlueprintRevisionNotionSyncTests(unittest.TestCase):
    def test_verified_revision_redelivery_requires_separate_notion_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionNotionSyncCommandService(Base(), store_path=Path(tmp) / "state.json")
            response = service.execute("status", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_approval_required")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("acknowledgement", response.message.casefold())

    def test_generic_approval_does_not_mutate_notion(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionNotionSyncCommandService(
                Base(), {"Notion": lambda dispatch: calls.append(dispatch) or {}}, store_path=Path(tmp) / "state.json"
            )
            service.execute("status", ())
            response = service.execute("do that", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_approval_required")
        self.assertEqual(calls, [])

    def test_scoped_approval_requires_exact_revision_delivery_evidence(self):
        calls = []

        def notion(dispatch):
            calls.append(dispatch)
            return {
                "verified": True,
                "mutation_count": 1,
                "record_id": "delivery-1",
                "status": "Growth Blueprint revision delivered",
            }

        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionNotionSyncCommandService(
                Base(), {"Notion": notion}, store_path=Path(tmp) / "state.json"
            )
            service.execute("status", ())
            response = service.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_verified")
        self.assertTrue(response.data["external_action_taken"])
        self.assertEqual(response.data["notion_record_id"], "delivery-1")
        self.assertEqual(calls[0]["payload"]["revision_file_id"], "file-r2")
        self.assertEqual(calls[0]["payload"]["original_delivered_file_id"], "file-r1")
        self.assertEqual(calls[0]["approval_scope"], "verified_growth_blueprint_revision_delivery_state_sync")

    def test_wrong_returned_status_does_not_become_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionNotionSyncCommandService(
                Base(),
                {"Notion": lambda dispatch: {"verified": True, "mutation_count": 1, "record_id": "delivery-1", "status": "Growth Blueprint delivered"}},
                store_path=Path(tmp) / "state.json",
            )
            service.execute("status", ())
            response = service.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_sync_unverified")
        self.assertFalse(response.data["external_action_taken"])

    def test_missing_notion_dispatcher_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintRevisionNotionSyncCommandService(Base(), store_path=Path(tmp) / "state.json")
            service.execute("status", ())
            response = service.execute("record Growth Blueprint revision delivery", ())
        self.assertEqual(response.data["execution_status"], "blueprint_revision_notion_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])

    def test_verified_sync_is_replay_safe_across_restart(self):
        calls = []

        def notion(dispatch):
            calls.append(dispatch)
            return {
                "verified": True,
                "mutation_count": 1,
                "record_id": "delivery-1",
                "status": "Growth Blueprint revision delivered",
            }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            first = TonyBlueprintRevisionNotionSyncCommandService(Base(), {"Notion": notion}, store_path=path)
            first.execute("status", ())
            first.execute("record Growth Blueprint revision delivery", ())
            restarted = TonyBlueprintRevisionNotionSyncCommandService(Base(), {"Notion": notion}, store_path=path)
            response = restarted.execute("status", ())
        self.assertEqual(len(calls), 1)
        self.assertEqual(response.data["execution_status"], "blueprint_revision_client_delivery_verified")


if __name__ == "__main__":
    unittest.main()
