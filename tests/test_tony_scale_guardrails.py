from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_learning import TonyExecutiveLearningCommandService


class PositiveOutcomeStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        if command == "outcome_result":
            return CommandResponse(
                "executive_outcome_review",
                "healthy",
                "Outcome review recorded.",
                {
                    "accepted": True,
                    "outcome": {
                        "action_id": "a-1",
                        "outcome_status": "positive",
                        "summary": "The matched business signal improved.",
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "priority": {"key": "growth:outreach", "label": "Founder outreach"},
                    },
                },
            )
        if command == "do_first":
            return CommandResponse(
                "agency_focus_action",
                "healthy",
                "I have prepared the handoff.",
                {
                    "priority": {"key": "growth:outreach", "label": "Founder outreach"},
                    "execution_status": "ready_for_handoff",
                    "external_action_taken": False,
                },
            )
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyMeasuredScaleGuardrailTests(unittest.TestCase):
    def test_scale_candidate_is_bounded_before_any_external_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyExecutiveLearningCommandService(
                PositiveOutcomeStub(),
                store_path=Path(tmp) / "learning.json",
            )
            for _ in range(4):
                service.execute("outcome_result", [])

            response = service.execute("do_first", [])

            guard = response.data["learning_guard"]
            scale = guard["scale_guardrails"]
            self.assertEqual(guard["status"], "measured_scale_candidate")
            self.assertEqual(scale["mode"], "measured_incremental_scale")
            self.assertEqual(scale["exposure_step"], "one_increment_only")
            self.assertEqual(scale["review_checkpoint"], "after_next_matched_outcome")
            self.assertTrue(scale["preserve_working_elements"])
            self.assertTrue(scale["preserve_success_signal"])
            self.assertTrue(scale["approval_required_before_external_scale"])
            self.assertFalse(scale["external_action_taken"])
            self.assertFalse(response.data["external_action_taken"])
            self.assertIn("one controlled increment", response.message.lower())
            self.assertIn("explicit approval", response.message.lower())
            self.assertIn("stop or adapt", response.message.lower())

    def test_scale_guardrails_do_not_appear_before_evidence_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TonyExecutiveLearningCommandService(
                PositiveOutcomeStub(),
                store_path=Path(tmp) / "learning.json",
            )
            for _ in range(3):
                service.execute("outcome_result", [])

            response = service.execute("do_first", [])

            self.assertEqual(response.data["learning_guard"]["status"], "positive_pattern_emerging")
            self.assertNotIn("scale_guardrails", response.data)


if __name__ == "__main__":
    unittest.main()
