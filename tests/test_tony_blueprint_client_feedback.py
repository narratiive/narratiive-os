from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.tony_blueprint_client_feedback import TonyBlueprintClientFeedbackCommandService
from runtime.tony_command_service import CommandResponse


class DeliveredBlueprintStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "blueprint_delivery_notion_sync",
            "healthy",
            "Notion now records the Growth Blueprint as delivered.",
            {
                "execution_status": "blueprint_delivery_notion_sync_verified",
                "notion_record_id": "notion-delivery-1",
                "blueprint_delivery_state": {
                    "delivery_project_record_id": "delivery-1",
                    "lead_id": "lead-1",
                    "contact": "Alex Example",
                    "company": "Example Co",
                    "growth_blueprint_file_id": "file-1",
                    "delivery_url": "https://drive.example/file-1",
                    "status": "Growth Blueprint delivered",
                },
                "external_action_taken": True,
            },
        )


class TonyBlueprintClientFeedbackTests(unittest.TestCase):
    def test_missing_gmail_dispatcher_never_infers_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyBlueprintClientFeedbackCommandService(
                DeliveredBlueprintStub(), {}, store_path=Path(tmp) / "feedback.json"
            )
            result = service.execute("record Growth Blueprint delivery", ())
            self.assertEqual(result.data["execution_status"], "blueprint_feedback_monitor_dispatcher_unavailable")
            self.assertFalse(result.data["blueprint_feedback"]["client_acknowledged"])
            self.assertFalse(result.data["blueprint_feedback"]["client_accepted"])
            self.assertFalse(result.data["external_action_taken"])

    def test_verified_acknowledgement_is_not_treated_as_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def gmail(dispatch):
                calls.append(dispatch)
                self.assertEqual(dispatch["execution_mode"], "autonomous_read")
                self.assertEqual(dispatch["payload"]["growth_blueprint_file_id"], "file-1")
                body = "Thanks, we received the Growth Blueprint and have it with the team."
                return {
                    "feedback_found": True,
                    "message_id": "feedback-1",
                    "thread_id": "thread-1",
                    "sender": "alex@example.com",
                    "body": body,
                    "summary": body,
                    "read_only": True,
                }

            service = TonyBlueprintClientFeedbackCommandService(
                DeliveredBlueprintStub(), {"Gmail": gmail}, store_path=Path(tmp) / "feedback.json"
            )
            result = service.execute("record Growth Blueprint delivery", ())
            self.assertEqual(result.data["execution_status"], "blueprint_client_feedback_verified")
            feedback = result.data["blueprint_feedback"]
            self.assertEqual(feedback["disposition"], "delivery_acknowledged")
            self.assertTrue(feedback["client_acknowledged"])
            self.assertFalse(feedback["client_accepted"])
            self.assertFalse(feedback["revision_requested"])
            self.assertFalse(result.data["external_action_taken"])
            self.assertIn("do not infer acceptance", result.message.casefold())
            self.assertEqual(len(calls), 1)

    def test_verified_revision_request_remains_internal_and_unaccepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            def gmail(dispatch):
                body = "Thanks. Could you revise the audience section and clarify the commercial implications?"
                return {
                    "feedback_found": True,
                    "message_id": "feedback-2",
                    "thread_id": "thread-2",
                    "sender": "alex@example.com",
                    "body": body,
                    "summary": body,
                    "read_only": True,
                }

            service = TonyBlueprintClientFeedbackCommandService(
                DeliveredBlueprintStub(), {"Gmail": gmail}, store_path=Path(tmp) / "feedback.json"
            )
            result = service.execute("record Growth Blueprint delivery", ())
            feedback = result.data["blueprint_feedback"]
            self.assertEqual(feedback["disposition"], "feedback_or_revision_request")
            self.assertTrue(feedback["revision_requested"])
            self.assertFalse(feedback["client_accepted"])
            self.assertFalse(result.data["external_action_taken"])
            self.assertIn("internal revision plan", result.message)

    def test_no_feedback_keeps_monitor_active_without_external_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            def gmail(dispatch):
                return {
                    "feedback_found": False,
                    "message_id": "search-1",
                    "thread_id": "thread-1",
                    "summary": "No matching inbound client feedback found.",
                    "read_only": True,
                }

            service = TonyBlueprintClientFeedbackCommandService(
                DeliveredBlueprintStub(), {"Gmail": gmail}, store_path=Path(tmp) / "feedback.json"
            )
            result = service.execute("record Growth Blueprint delivery", ())
            self.assertEqual(result.data["execution_status"], "blueprint_feedback_monitor_active")
            self.assertFalse(result.data["blueprint_feedback"]["client_acknowledged"])
            self.assertFalse(result.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
