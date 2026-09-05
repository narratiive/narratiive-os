from __future__ import annotations

import tempfile
import unittest

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_workflow_runtime import build_tony_workflow_runtime


def _lifecycle(client_id: str) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name="SAFE Synthetic Company",
        stage=ClientLifecycleStage.LEAD,
        owner="Tony",
        next_action="Prepare the next internal work product",
        evidence=("synthetic:test",),
    )


def _blueprint_output() -> dict[str, object]:
    return {
        "blueprint_lite": "A substantive evidence-disciplined Blueprint Lite with a clear growth argument.",
        "diagnostic_signals_used": ["Overall score", "Main blockage", "Raw answer evidence"],
        "diagnostic_input_coverage": {"complete": True},
        "source_backed_evidence": [{"source": "https://example.com", "fact": "Reserved example domain"}],
        "evidence_gaps": ["Real company context is intentionally absent from this synthetic test."],
        "fact_interpretation_hypothesis_lineage": {
            "fact": ["The supplied diagnostic reports a blockage."],
            "interpretation": ["The blockage may be constraining demand."],
            "hypothesis": ["A clearer position could improve response."],
        },
        "growth_tension": "The company needs growth while its message remains indistinct.",
        "provisional_opportunity": "Test one sharper evidence-led position before scaling activity.",
        "questions_to_answer_next": [
            "Which segment responds best?",
            "What evidence predicts choice?",
            "Where does the current message fail?",
        ],
        "quality_gate": {"human_review_ready": True},
        "recommendation": "advance",
    }


class TonyWorkflowRuntimeIntegrationTests(unittest.TestCase):
    def test_blueprint_lite_executes_through_registered_generic_runtime_and_pauses(self) -> None:
        calls = []

        def claude(contract):
            calls.append(contract)
            return _blueprint_output()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": claude},
                environ={},
            )
            registry_ids = {item.workflow_id for item in runtime.coordinator.registry.all()}
            self.assertEqual(len(registry_ids), 10)
            runtime.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-blueprint-run",
                {"diagnostic_input_package": {"overall_score": 42, "raw_answers": {"challenge": "safe"}}},
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-blueprint-run", _lifecycle("safe-client"))
            self.assertEqual(outcome.status, "awaiting_approval")
            self.assertEqual(outcome.action, "await_human_approval")
            self.assertFalse(outcome.external_action_taken)
            state = runtime.status("safe-blueprint-run")
            self.assertEqual(state["approval_status"], "pending")
            self.assertTrue(state["stages"][0]["quality_result"]["passed"])
            self.assertEqual(len(state["stages"][0]["output_artifacts"]), 1)
            self.assertEqual(calls[0]["worker"], "Claude")
            self.assertEqual(calls[0]["execution_mode"], "autonomous_prepare")

            restarted = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": claude},
                environ={},
            )
            self.assertEqual(restarted.status("safe-blueprint-run")["approval_status"], "pending")
            restarted.approve(
                "safe-blueprint-run",
                approver="authorised-human",
                rationale="Synthetic integration test only",
            )
            self.assertEqual(restarted.status("safe-blueprint-run")["status"], "complete")
            self.assertEqual(len(calls), 1)

    def test_unimplemented_quality_contract_blocks_before_worker_execution(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="safe-client",
                dispatchers={"Claude": lambda contract: calls.append(contract) or {"discovery_hypotheses": ["x"]}},
                environ={},
            )
            runtime.enqueue(
                "blueprint_lite_to_discovery_preparation",
                "safe-discovery-run",
                {
                    "blueprint_lite": "safe",
                    "diagnostic_evidence": {"source": "synthetic"},
                    "company_context": {"name": "SAFE Synthetic Company"},
                },
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            outcome = runtime.advance("safe-discovery-run", _lifecycle("safe-client"))
            self.assertEqual(
                outcome.blocker,
                "quality_validator_unavailable:discovery_preparation_quality_gate",
            )
            self.assertEqual(calls, [])
            self.assertFalse(outcome.external_action_taken)

    def test_workspace_client_scopes_are_durably_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="client-one",
                dispatchers={},
                environ={},
            )
            second = build_tony_workflow_runtime(
                tmp,
                workspace_id="agency",
                client_id="client-two",
                dispatchers={},
                environ={},
            )
            first.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "shared-run-id",
                {"diagnostic_input_package": {"safe": "one"}},
                entity_id="lead-one",
                correlation_id="corr-one",
            )
            second.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "shared-run-id",
                {"diagnostic_input_package": {"safe": "two"}},
                entity_id="lead-two",
                correlation_id="corr-two",
            )
            self.assertEqual(first.status("shared-run-id")["entity_id"], "lead-one")
            self.assertEqual(second.status("shared-run-id")["entity_id"], "lead-two")


if __name__ == "__main__":
    unittest.main()
