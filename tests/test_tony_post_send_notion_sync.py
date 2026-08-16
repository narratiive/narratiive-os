from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_post_send_notion_sync import TonyPostSendNotionSyncCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, response: CommandResponse) -> None:
        self.response = response
        self.calls = []

    def execute(self, command, objects):
        self.calls.append((command, list(objects)))
        return self.response


def verified_gmail_response() -> CommandResponse:
    return CommandResponse(
        command="autonomous_result_action",
        status="healthy",
        message="Gmail completed the approved action and returned verified execution evidence.",
        data={
            "execution_status": "approved_step_verified",
            "dispatch_result": {
                "worker": "Gmail",
                "status": "verified",
                "evidence": {"sent": True, "message_id": "gmail-123"},
            },
            "execution_handoff": {
                "worker": "Gmail",
                "approval_required": True,
                "approval_granted": True,
                "execution_truth": "verified_dispatch",
                "dispatch": {
                    "worker": "Gmail",
                    "execution_mode": "approval_gated_write",
                    "state": "dispatch_verified",
                    "execution_truth": "verified_dispatch",
                    "target": {
                        "lead_id": "lead-1",
                        "contact": "Alex Example",
                        "company": "Example Co",
                        "area": "commercial",
                    },
                    "payload": {
                        "kind": "reviewed_outreach_email",
                        "subject": "A sharper growth story for Example Co",
                        "body": "Hi Alex, reviewed copy.",
                    },
                },
            },
        },
    )


class TonyPostSendNotionSyncTests(unittest.TestCase):
    NOW = datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)

    def _service(self, dispatchers=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        stub = StubCommandService(verified_gmail_response())
        service = TonyPostSendNotionSyncCommandService(
            stub,
            dispatchers=dispatchers,
            store_path=Path(tmp.name) / "post-send-sync.json",
            clock=lambda: self.NOW,
        )
        return service, stub

    def test_verified_gmail_send_prepares_notion_update_without_mutating_notion(self):
        notion_calls = []
        service, _ = self._service({"Notion": lambda contract: notion_calls.append(contract) or {"updated": True, "page_id": "notion-456"}})

        response = service.execute("OK, send it", ())

        self.assertEqual(notion_calls, [])
        self.assertEqual(response.data["execution_status"], "gmail_verified_notion_approval_required")
        sync = response.data["commercial_state_sync"]
        self.assertEqual(sync["state"], "awaiting_approval")
        self.assertEqual(sync["gmail_message_id"], "gmail-123")
        self.assertEqual(sync["lead_id"], "lead-1")
        self.assertEqual(sync["status"], "Contacted")
        self.assertFalse(sync["external_action_taken"])
        self.assertIn("I have not changed the commercial record yet", response.message)

    def test_explicit_approval_updates_notion_with_verified_gmail_receipt(self):
        notion_calls = []

        def notion(contract):
            notion_calls.append(contract)
            self.assertEqual(contract["execution_mode"], "approval_gated_write")
            self.assertTrue(contract["approval_granted"])
            self.assertEqual(contract["approval_scope"], "post_send_commercial_state_sync")
            self.assertEqual(contract["payload"]["status"], "Contacted")
            self.assertEqual(contract["payload"]["gmail_message_id"], "gmail-123")
            self.assertEqual(contract["target"]["lead_id"], "lead-1")
            return {"updated": True, "page_id": "notion-456"}

        service, stub = self._service({"Notion": notion})
        service.execute("OK, send it", ())
        response = service.execute("do that", ())

        self.assertEqual(len(notion_calls), 1)
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(response.data["execution_status"], "commercial_state_sync_verified")
        self.assertEqual(response.data["notion_receipt"], "notion-456")
        self.assertEqual(response.data["gmail_message_id"], "gmail-123")
        self.assertEqual(response.data["follow_up_commitment"]["status"], "pending")
        self.assertTrue(response.data["external_action_taken"])
        self.assertIn("authoritative Notion lead record is now updated", response.message)

    def test_missing_notion_dispatcher_keeps_update_pending_without_false_claim(self):
        service, stub = self._service()
        service.execute("OK, send it", ())
        response = service.execute("do that", ())

        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(response.data["execution_status"], "notion_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("update remains pending", response.message)

    def test_completed_gmail_receipt_is_not_requeued_after_success(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Path(tmp.name) / "post-send-sync.json"
        calls = []

        def notion(contract):
            calls.append(contract)
            return {"updated": True, "page_id": "notion-456"}

        stub = StubCommandService(verified_gmail_response())
        service = TonyPostSendNotionSyncCommandService(stub, dispatchers={"Notion": notion}, store_path=store, clock=lambda: self.NOW)
        service.execute("OK, send it", ())
        service.execute("do that", ())

        restarted = TonyPostSendNotionSyncCommandService(stub, dispatchers={"Notion": notion}, store_path=store, clock=lambda: self.NOW)
        replay = restarted.execute("status", ())

        self.assertEqual(len(calls), 1)
        self.assertNotIn("commercial_state_sync", replay.data)


if __name__ == "__main__":
    unittest.main()
