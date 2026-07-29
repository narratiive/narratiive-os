import unittest

from runtime.client_lifecycle import ClientLifecycleStage
from runtime.client_lifecycle_commands import ClientLifecycleCommandService
from runtime.client_lifecycle_fixtures import deterministic_test_clients


class ClientLifecycleCommandTests(unittest.TestCase):
    def test_status_reports_stage_value_and_next_action(self):
        service = ClientLifecycleCommandService(deterministic_test_clients)

        result = service.status("northstar")

        self.assertEqual(result.status, "healthy")
        self.assertIn("proposal", result.message)
        self.assertIn("£6,000", result.message)
        self.assertIn("Send the Growth Blueprint proposal", result.message)

    def test_advance_requires_evidence_and_persists_one_step_transition(self):
        saved = []
        service = ClientLifecycleCommandService(deterministic_test_clients, saved.append)

        with self.assertRaisesRegex(ValueError, "requires evidence"):
            service.advance(
                "northstar",
                ClientLifecycleStage.DELIVERY,
                next_action="Begin delivery.",
                evidence="",
            )

        result = service.advance(
            "northstar",
            ClientLifecycleStage.DELIVERY,
            next_action="Begin delivery.",
            evidence="proposal:accepted",
        )

        self.assertEqual(result.record.stage, ClientLifecycleStage.DELIVERY)
        self.assertEqual(saved[0].evidence[-1], "proposal:accepted")

    def test_advance_fails_closed_without_persistence(self):
        service = ClientLifecycleCommandService(deterministic_test_clients)

        with self.assertRaisesRegex(RuntimeError, "persistence is not configured"):
            service.advance(
                "northstar",
                ClientLifecycleStage.DELIVERY,
                next_action="Begin delivery.",
                evidence="proposal:accepted",
            )


if __name__ == "__main__":
    unittest.main()
