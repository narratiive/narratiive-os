from __future__ import annotations

import unittest

from runtime.tony_command_service import CommandResponse
from runtime.tony_outcome_evidence import TonyOutcomeEvidenceCommandService


class StubOutcomeService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, *, adaptive: bool = True, success_signal: str = "Reply rate >= 20%") -> None:
        self._awaiting_outcome = {
            "adaptive_test": adaptive,
            "success_signal": success_signal,
        }
        self.received = None

    def execute(self, command, objects):
        self.received = tuple(objects)
        payload = self.received[0] if self.received else {}
        nested = payload.get("executive_outcome") if isinstance(payload, dict) else None
        result = nested if isinstance(nested, dict) else payload
        state = str(result.get("outcome_status") or "") if isinstance(result, dict) else ""
        return CommandResponse(
            "executive_outcome_review",
            "healthy" if state == "positive" else "attention",
            f"Outcome recorded as {state}.",
            {"accepted": True, "business_outcome_status": state},
        )


class TonyOutcomeEvidenceTests(unittest.TestCase):
    def test_measured_success_overrides_caller_negative_label(self):
        inner = StubOutcomeService()
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "adaptive-1",
                "outcome_status": "negative",
                "evidence": {
                    "measurement": {
                        "observed_value": 0.28,
                        "target_value": 0.20,
                        "operator": ">=",
                    }
                },
            }],
        )

        self.assertEqual(response.data["business_outcome_status"], "positive")
        self.assertTrue(response.data["outcome_interpretation"]["derived"])
        self.assertTrue(response.data["outcome_interpretation"]["criterion_met"])
        self.assertEqual(inner.received[0]["outcome_status"], "positive")
        self.assertIn("derived the outcome", response.message)

    def test_measured_failure_overrides_caller_positive_label(self):
        inner = StubOutcomeService()
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "adaptive-1",
                "outcome_status": "positive",
                "evidence": {
                    "measurement": {
                        "observed_value": 0.12,
                        "target_value": 0.20,
                        "operator": ">=",
                    }
                },
            }],
        )

        self.assertEqual(response.data["business_outcome_status"], "negative")
        self.assertFalse(response.data["outcome_interpretation"]["criterion_met"])
        self.assertEqual(inner.received[0]["outcome_status"], "negative")

    def test_unmeasured_adaptive_evidence_is_inconclusive_not_asserted_success(self):
        inner = StubOutcomeService()
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "adaptive-1",
                "outcome_status": "positive",
                "evidence": {"note": "The team felt it performed better."},
            }],
        )

        self.assertEqual(response.data["business_outcome_status"], "inconclusive")
        self.assertFalse(response.data["outcome_interpretation"]["derived"])
        self.assertEqual(inner.received[0]["outcome_status"], "inconclusive")
        self.assertIn("kept the judgement inconclusive", response.message)

    def test_non_adaptive_outcomes_keep_existing_contract(self):
        inner = StubOutcomeService(adaptive=False)
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "normal-1",
                "outcome_status": "positive",
                "evidence": {"reply_id": "reply-1"},
            }],
        )

        self.assertEqual(response.data["business_outcome_status"], "positive")
        self.assertEqual(inner.received[0]["outcome_status"], "positive")
        self.assertNotIn("outcome_interpretation", response.data)

    def test_nested_outcome_payload_is_interpreted(self):
        inner = StubOutcomeService()
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "record_outcome",
            [{
                "executive_outcome": {
                    "action_id": "adaptive-1",
                    "outcome_status": "positive",
                    "evidence": {
                        "measurement": {
                            "observed_value": 4,
                            "target_value": 5,
                            "operator": ">=",
                        }
                    },
                }
            }],
        )

        self.assertEqual(response.data["business_outcome_status"], "negative")
        self.assertEqual(
            inner.received[0]["executive_outcome"]["outcome_status"],
            "negative",
        )


if __name__ == "__main__":
    unittest.main()
