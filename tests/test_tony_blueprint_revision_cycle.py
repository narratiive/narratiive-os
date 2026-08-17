from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from runtime.tony_blueprint_revision_cycle import TonyBlueprintRevisionCycleCommandService
from runtime.tony_command_service import CommandResponse


class StubService:
    mission_control_loader = None
    github_configured = False
    def __init__(self, response): self.response = response
    def execute(self, command, objects): return self.response


def feedback_response(revision_requested=True):
    return CommandResponse("blueprint_client_feedback", "healthy", "Verified feedback.", {
        "execution_status": "blueprint_client_feedback_verified",
        "blueprint_feedback": {"revision_requested": revision_requested, "delivery_project_record_id": "proj-1", "growth_blueprint_file_id": "file-1", "delivery_url": "https://drive.test/file-1", "lead_id": "lead-1", "contact": "Alex", "company": "Acme"},
        "gmail_feedback_evidence": {"execution_truth": "verified", "verified": True, "message_id": "msg-1", "body": "Please revise the positioning section and clarify the evidence."},
    })


class TonyBlueprintRevisionCycleTests(unittest.TestCase):
    def make(self, response, dispatchers=None):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        return TonyBlueprintRevisionCycleCommandService(StubService(response), dispatchers or {}, store_path=Path(self.temp.name) / "revision.json")

    def test_non_revision_feedback_passes_through(self):
        service = self.make(feedback_response(False)); response = service.execute("check feedback", [])
        self.assertEqual(response.command, "blueprint_client_feedback")

    def test_missing_claude_fails_closed_without_artifact_change(self):
        service = self.make(feedback_response()); response = service.execute("check feedback", [])
        self.assertEqual(response.data["execution_status"], "blueprint_revision_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("not altered", response.message)

    def test_verified_revision_is_reviewed_and_held_for_fresh_approval(self):
        calls = []
        def claude(dispatch):
            calls.append(dispatch)
            return {"execution_truth": "verified", "verified": True, "provider_message_id": "claude-1", "growth_blueprint": "This is a complete revised Growth Blueprint working draft " * 12, "sources": ["verified source"], "evidence_gaps": ["client validation"], "narratiive_fit": "strong", "strategic_growth_opportunity": "clarify distinctive positioning", "recommendation": "advance"}
        service = self.make(feedback_response(), {"Claude": claude}); response = service.execute("check feedback", [])
        self.assertEqual(response.data["execution_status"], "blueprint_revision_ready_for_approval")
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(len(calls), 1); self.assertEqual(calls[0]["execution_mode"], "autonomous_prepare")
        self.assertIn("fresh approval", response.message)

    def test_weak_revision_cannot_replace_or_redeliver(self):
        def claude(dispatch): return {"execution_truth": "verified", "verified": True, "provider_message_id": "claude-2", "growth_blueprint": "too short", "recommendation": "advance"}
        service = self.make(feedback_response(), {"Claude": claude}); response = service.execute("check feedback", [])
        self.assertEqual(response.data["execution_status"], "blueprint_revision_requires_rework")
        self.assertFalse(response.data["external_action_taken"])


if __name__ == "__main__": unittest.main()
