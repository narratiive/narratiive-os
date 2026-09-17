from __future__ import annotations

import unittest

from runtime.workflow_run_identity import MAX_PERSISTED_RUN_ID_LENGTH, downstream_run_id


class WorkflowRunIdentityTests(unittest.TestCase):
    def test_short_downstream_identity_preserves_legacy_shape(self) -> None:
        self.assertEqual(
            downstream_run_id("source-run", "next-workflow"),
            "source-run-next-workflow",
        )

    def test_long_downstream_identity_is_bounded_deterministic_and_target_readable(self) -> None:
        source = "northstar-test-" + ("long-workflow-chain-" * 20)
        first = downstream_run_id(source, "growth_blueprint_deliverable_production")
        replay = downstream_run_id(source, "growth_blueprint_deliverable_production")
        other = downstream_run_id(source, "growth_blueprint_to_campaign_world")

        self.assertEqual(first, replay)
        self.assertLessEqual(len(first), MAX_PERSISTED_RUN_ID_LENGTH)
        self.assertIn("growth_blueprint_deliverable_production", first)
        self.assertNotEqual(first, other)


if __name__ == "__main__":
    unittest.main()
