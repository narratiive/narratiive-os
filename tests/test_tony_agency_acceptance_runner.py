from __future__ import annotations

import unittest

from scripts.run_tony_agency_acceptance import _has_external_effect


class TonyAgencyAcceptanceRunnerTests(unittest.TestCase):
    def test_negative_external_action_attestation_is_not_a_false_positive(self) -> None:
        self.assertFalse(_has_external_effect({"quality_gate": {"no_external_action_taken": True}, "external_action_taken": False}))

    def test_verified_external_action_is_detected(self) -> None:
        self.assertTrue(_has_external_effect({"receipt": {"external_action_taken": True}}))
        self.assertTrue(_has_external_effect({"event_type": "email_sent"}))


if __name__ == "__main__":
    unittest.main()
