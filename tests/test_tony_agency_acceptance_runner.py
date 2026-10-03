from __future__ import annotations

import unittest

from scripts.run_tony_agency_acceptance import STAGE_WORKFLOWS, _has_external_effect


class TonyAgencyAcceptanceRunnerTests(unittest.TestCase):
    def test_negative_external_action_attestation_is_not_a_false_positive(self) -> None:
        self.assertFalse(_has_external_effect({"quality_gate": {"no_external_action_taken": True}, "external_action_taken": False}))

    def test_verified_external_action_is_detected(self) -> None:
        self.assertTrue(_has_external_effect({"receipt": {"external_action_taken": True}}))
        self.assertTrue(_has_external_effect({"event_type": "email_sent"}))

    def test_client_operations_uses_the_registered_discovery_preparation_workflow_id(self) -> None:
        self.assertIn("blueprint_lite_to_discovery_preparation", STAGE_WORKFLOWS["Client operations"])
        self.assertNotIn("blueprint_lite_to_discovery_prep", STAGE_WORKFLOWS["Client operations"])


if __name__ == "__main__":
    unittest.main()
