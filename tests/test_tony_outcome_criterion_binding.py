from __future__ import annotations

import unittest

from runtime.tony_command_service import CommandResponse
from runtime.tony_outcome_evidence import TonyOutcomeEvidenceCommandService


class StubOutcomeService:
    mission_control_loader = None
    github_configured = False

    def __init__(self, success_signal: str) -> None:
        self._awaiting_outcome = {
            "adaptive_test": True,
            "success_signal": success_signal,
        }
        self.received = None

    def execute(self, command, objects):
        self.received = tuple(objects)
        payload = self.received[0] if self.received else {}
        state = str(payload.get("outcome_status") or "")
        return CommandResponse(
            "executive_outcome_review",
            "healthy" if state == "positive" else "attention",
            f"Outcome recorded as {state}.",
            {"business_outcome_status": state},
        )


class TonyOutcomeCriterionBindingTests(unittest.TestCase):
    def test_numeric_threshold_comes_from_agreed_success_signal(self):
        inner = StubOutcomeService("Reply rate >= 20%")
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "adaptive-criterion-1",
                "outcome_status": "positive",
                "evidence": {
                    "measurement": {
                        "observed_value": 0.15,
                        "target_value": 0.10,
                        "operator": ">=",
                    }
                },
            }],
        )

        interpretation = response.data["outcome_interpretation"]
        self.assertEqual(response.data["business_outcome_status"], "negative")
        self.assertEqual(interpretation["target_value"], 0.20)
        self.assertEqual(interpretation["supplied_target_value"], 0.10)
        self.assertTrue(interpretation["criterion_bound_to_success_signal"])

    def test_numeric_operator_cannot_be_weakened_by_caller(self):
        inner = StubOutcomeService("Qualified calls >= 5")
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "adaptive-criterion-2",
                "outcome_status": "positive",
                "evidence": {
                    "measurement": {
                        "observed_value": 4,
                        "target_value": 5,
                        "operator": "<=",
                    }
                },
            }],
        )

        interpretation = response.data["outcome_interpretation"]
        self.assertEqual(response.data["business_outcome_status"], "negative")
        self.assertEqual(interpretation["operator"], ">=")
        self.assertEqual(interpretation["supplied_operator"], "<=")

    def test_event_window_comes_from_agreed_success_signal(self):
        inner = StubOutcomeService("Qualified positive reply within three business days")
        service = TonyOutcomeEvidenceCommandService(inner)

        response = service.execute(
            "outcome_result",
            [{
                "action_id": "adaptive-criterion-3",
                "outcome_status": "positive",
                "evidence": {
                    "measurement": {
                        "type": "qualified_event_within_business_days",
                        "event_observed": True,
                        "event_qualified": True,
                        "business_days_elapsed": 5,
                        "max_business_days": 10,
                    }
                },
            }],
        )

        interpretation = response.data["outcome_interpretation"]
        self.assertEqual(response.data["business_outcome_status"], "negative")
        self.assertEqual(interpretation["max_business_days"], 3)
        self.assertEqual(interpretation["supplied_max_business_days"], 10)
        self.assertTrue(interpretation["criterion_bound_to_success_signal"])


if __name__ == "__main__":
    unittest.main()
