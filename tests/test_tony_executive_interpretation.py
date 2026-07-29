import unittest

from runtime.executive_message import ExecutiveUrgency
from runtime.tony_executive_interpretation import interpret_observability_result


class TonyExecutiveInterpretationTests(unittest.TestCase):
    def test_health_projection_is_evidence_linked_and_business_facing(self):
        message = interpret_observability_result(
            action="health",
            data={"status": "ok", "provider_debug": "secret-internal-value"},
            evidence_reference="gateway:health:tony-health-1",
        )

        self.assertEqual(message.urgency, ExecutiveUrgency.ROUTINE)
        self.assertIn("continue normal orchestration", message.implication)
        self.assertEqual(message.evidence[0].reference, "gateway:health:tony-health-1")
        self.assertNotIn("provider_debug", message.render_compact())
        self.assertNotIn("secret-internal-value", message.render_compact())

    def test_blocked_run_recommends_review_without_changing_approval_boundary(self):
        message = interpret_observability_result(
            action="run.status",
            data={"status": "awaiting_approval"},
            evidence_reference="gateway:runs.get:tony-run-1",
        )

        self.assertEqual(message.urgency, ExecutiveUrgency.TODAY)
        self.assertFalse(message.interruption_eligible)
        self.assertIn("resolve the outstanding gate", message.recommendation)
        self.assertNotIn("approve automatically", message.recommendation.lower())

    def test_failed_job_is_actionable_but_advisory(self):
        message = interpret_observability_result(
            action="job.get",
            data={"status": "failed", "traceback": "Traceback: provider internals"},
            evidence_reference="gateway:jobs.get:tony-job-1",
        )

        rendered = message.render_compact()
        self.assertEqual(message.urgency, ExecutiveUrgency.TODAY)
        self.assertIn("recovery or cancellation", message.recommendation)
        self.assertNotIn("Traceback", rendered)
        self.assertNotIn("provider internals", rendered)

    def test_approval_queue_count_is_bounded_and_deterministic(self):
        message = interpret_observability_result(
            action="approval.list",
            data={"count": 5000},
            evidence_reference="gateway:approvals.list:tony-approvals-1",
        )

        self.assertIn("999 approval items", message.observation)
        self.assertEqual(message.urgency, ExecutiveUrgency.TODAY)

    def test_approval_state_preserves_human_decision(self):
        message = interpret_observability_result(
            action="approval.get",
            data={"current": {"status": "awaiting_approval"}},
            evidence_reference="gateway:approvals.get:tony-approval-1",
        )

        self.assertIn("approve, revise, comment, or block", message.recommendation)
        self.assertFalse(message.interruption_eligible)

    def test_rejects_unsupported_actions_and_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, "unsupported observability action"):
            interpret_observability_result(
                action="blueprint.export",
                data={},
                evidence_reference="gateway:blueprints.export:tony-export-1",
            )

        with self.assertRaisesRegex(ValueError, "evidence_reference"):
            interpret_observability_result(
                action="health",
                data={"status": "ok"},
                evidence_reference=" ",
            )


if __name__ == "__main__":
    unittest.main()
