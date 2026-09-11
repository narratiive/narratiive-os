from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime


def blueprint_output(*, suffix: str = "") -> dict:
    return {
        "blueprint_lite": "A substantial internal review artefact. " + (suffix * 3000),
        "central_diagnosis": "The category argument is stronger than the proprietary brand argument.",
        "diagnostic_signals_used": ["positioning clarity", "retention tension"],
        "diagnostic_input_coverage": {"complete": True},
        "source_backed_evidence": [{"source": "synthetic:test", "fact": "Explicit fixture evidence"}],
        "evidence_gaps": ["Founder evidence is not yet available"],
        "fact_interpretation_hypothesis_lineage": {
            "fact": ["Synthetic fact"],
            "interpretation": ["Synthetic interpretation"],
            "hypothesis": ["Synthetic hypothesis"],
        },
        "growth_tension": "Acquisition is working harder than retention.",
        "provisional_opportunity": "Build a proprietary retention story.",
        "questions_to_answer_next": ["Who stays?", "Why leave?", "What compounds?"],
        "quality_gate": {"human_review_ready": True},
        "recommendation": "advance",
    }


class Fallback:
    def execute(self, command, objects):
        return CommandResponse("conversation", "healthy", command, {})


class TonyInternalReviewDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gmail_calls: list[dict] = []
        self.version = 0

        def claude(_contract):
            self.version += 1
            return blueprint_output(suffix=str(self.version))

        def gmail(contract):
            self.gmail_calls.append(contract)
            return {
                "verified": True,
                "sent": True,
                "mutation_count": 1,
                "message_id": "gmail-safe-1",
                "thread_id": "thread-safe-1",
            }

        self.dispatchers = {"Claude": claude, "Gmail": gmail}
        self.runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=self.dispatchers,
            environ={},
        )
        self.runtime.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            "safe-review-run",
            {"diagnostic_input_package": {"overall_score": 40}, "company": "SAFE Review Company"},
            entity_id="safe-lead",
            correlation_id="safe-correlation",
        )
        self.runtime.advance(
            "safe-review-run",
            ClientLifecycleRecord(
                client_id="safe-client",
                client_name="SAFE Review Company",
                stage=ClientLifecycleStage.RESEARCH,
                owner="Tony",
                next_action="Prepare internal work",
                evidence=("synthetic:test",),
            ),
        )
        self.service = TonyWorkflowCommandService(
            Fallback(),
            FileWorkflowCommandBackend(self.root, dispatchers=self.dispatchers, environ={}),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_substantial_artifact_is_attached_and_telegram_response_stays_concise(self) -> None:
        response = self.service.execute(
            "/deliver-review safe-review-run",
            [],
            inputs={"recipient": "hello@narratiive.com"},
        )

        self.assertEqual(response.status, "healthy")
        self.assertTrue(response.data["delivered"])
        self.assertLess(len(response.message), 3500)
        self.assertNotIn("A substantial internal review artefact", response.message)
        self.assertIn("hello@narratiive.com", response.message)
        self.assertEqual(len(self.gmail_calls), 1)
        payload = self.gmail_calls[0]["payload"]
        self.assertEqual(payload["recipient_email"], "hello@narratiive.com")
        self.assertEqual(payload["attachments"][0]["mime_type"], "text/html")
        self.assertNotIn("blueprint_lite", payload["body"])

    def test_delivery_is_exactly_once_across_restart(self) -> None:
        first = self.service.execute("/deliver-review safe-review-run", [])
        restarted = TonyWorkflowCommandService(
            Fallback(),
            FileWorkflowCommandBackend(self.root, dispatchers=self.dispatchers, environ={}),
        )
        second = restarted.execute("/deliver-review safe-review-run", [])

        self.assertTrue(first.data["delivered"])
        self.assertTrue(second.data["delivered"])
        self.assertTrue(second.data["duplicate_suppressed"])
        self.assertEqual(len(self.gmail_calls), 1)
        state = self.runtime.runs.load_run("safe-review-run")
        self.assertEqual(len(state.external_action_receipts), 1)

    def test_non_allowlisted_recipient_fails_closed(self) -> None:
        response = self.service.execute(
            "/deliver-review safe-review-run",
            [],
            inputs={"recipient": "external@example.com"},
        )

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "workflow_command_rejected")
        self.assertEqual(self.gmail_calls, [])

    def test_gmail_failure_is_explicit_and_never_claims_delivery(self) -> None:
        def failed(_contract):
            raise RuntimeError("synthetic provider failure")

        service = TonyWorkflowCommandService(
            Fallback(),
            FileWorkflowCommandBackend(
                self.root,
                dispatchers={"Claude": self.dispatchers["Claude"], "Gmail": failed},
                environ={},
            ),
        )
        response = service.execute("/deliver-review safe-review-run", [])

        self.assertEqual(response.status, "blocked")
        self.assertFalse(response.data["delivered"])
        self.assertIn("could not be verified as delivered", response.message)
        self.assertNotIn("I sent", response.message)

    def test_natural_decision_uses_exact_current_gate_token_and_stale_token_fails(self) -> None:
        gate = self.service.execute("/workflow safe-review-run", []).data
        old_token = gate["approval_token"]
        revised = self.service.execute(
            "/reject safe-review-run because centre the opportunity on retention",
            [],
            principal_id="telegram:123",
            inputs={"approval_token": old_token},
        )
        self.assertEqual(revised.data["status"], "active")

        self.runtime.advance(
            "safe-review-run",
            ClientLifecycleRecord(
                client_id="safe-client",
                client_name="SAFE Review Company",
                stage=ClientLifecycleStage.RESEARCH,
                owner="Tony",
                next_action="Revise internal work",
                evidence=("synthetic:test",),
            ),
        )
        current = self.service.execute("/workflow safe-review-run", []).data
        self.assertNotEqual(current["approval_token"], old_token)
        stale = self.service.execute(
            "/approve safe-review-run because the earlier version was strong",
            [],
            principal_id="telegram:123",
            inputs={"approval_token": old_token},
        )
        self.assertEqual(stale.status, "error")
        self.assertIn("stale", stale.message)
        self.assertEqual(self.runtime.runs.load_run("safe-review-run").approval_status, "pending")

    def test_ambiguous_decision_without_gate_token_fails_safe(self) -> None:
        response = self.service.execute(
            "/approve safe-review-run because looks fine I suppose",
            [],
            principal_id="telegram:123",
        )
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "approval_token_required")
        self.assertEqual(self.runtime.runs.load_run("safe-review-run").approval_status, "pending")


if __name__ == "__main__":
    unittest.main()
