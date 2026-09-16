from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_internal_review_delivery import workflow_approval_token
from runtime.tony_promised_work import TonyPromisedWorkWorker
from runtime.tony_workflow_commands import FileWorkflowCommandBackend
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_tony_workflow_commands import blueprint_output
from tests.test_workflow_quality import proposal_output
from runtime.workspaces import WorkspaceRuntimeManager
from scripts.run_tony_conversation_worker import resolve_workflow_workspace_id


def lifecycle() -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id="safe-client",
        client_name="SAFE Promised Work Company",
        stage=ClientLifecycleStage.BLUEPRINT_LITE,
        owner="Tony",
        next_action="Prepare authorised internal work",
        evidence=("synthetic:test",),
    )


def discovery_evidence() -> dict:
    return {
        "notes": "Synthetic Discovery established the priority audience, commercial tension and unresolved proof question.",
        "sources": [
            {
                "source_id": "telegram-session:synthetic:messages:1-8",
                "source_type": "conversation_transcript",
                "location": "openclaw-session:synthetic:messages:1-8",
            }
        ],
    }


class TonyPromisedWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gmail_calls: list[dict] = []
        self.telegram_messages: list[str] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _dispatchers(self, *, fail_specialist: bool = False):
        def claude(contract):
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if fail_specialist and workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                raise RuntimeError("synthetic specialist failure")
            return proposal_output() if workflow_id == "discovery_evidence_to_growth_sprint_proposal" else blueprint_output()

        def gmail(contract):
            self.gmail_calls.append(contract)
            return {"sent": True, "message_id": "gmail-safe-1", "thread_id": "thread-safe-1"}

        return {"Claude": claude, "Gmail": gmail}

    def _commission(self, dispatchers=None):
        dispatchers = dispatchers or self._dispatchers()
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        runtime.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            "safe-promised-source",
            {"diagnostic_input_package": {"overall_score": 42}, "company": "SAFE Promised Work Company"},
            entity_id="safe-lead",
            correlation_id="telegram-safe-conversation",
        )
        runtime.advance("safe-promised-source", lifecycle())
        runtime.approve("safe-promised-source", approver="matt", rationale="Synthetic source approval")
        state, replay = runtime.commission(
            "safe-promised-source",
            "discovery_evidence_to_growth_sprint_proposal",
            {"discovery_evidence": discovery_evidence(), "commercial_context": {"source": "synthetic:test"}},
            commitment_id="telegram-safe-commitment",
        )
        return state, replay, dispatchers

    def _sender(self, message: str):
        self.telegram_messages.append(message)
        return {"message_id": "telegram-safe-1", "date": 1}

    def test_commitment_is_durable_before_acknowledgement_and_idempotent(self) -> None:
        state, replay, _ = self._commission()
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=self._dispatchers(),
            environ={},
        )
        repeated, repeated_replay = runtime.commission(
            "safe-promised-source",
            "discovery_evidence_to_growth_sprint_proposal",
            {"discovery_evidence": discovery_evidence(), "commercial_context": {"source": "synthetic:test"}},
            commitment_id="telegram-safe-commitment",
        )

        self.assertFalse(replay)
        self.assertEqual(state.status.value, "active")
        self.assertEqual(state.input_payload["_promised_work"]["state"], "commissioned")
        self.assertTrue(repeated_replay)
        self.assertEqual(repeated.run_id, state.run_id)

    def test_restart_recovers_work_delivers_gate_once_and_stops_for_human(self) -> None:
        state, _, dispatchers = self._commission()
        backend_after_restart = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )
        worker = TonyPromisedWorkWorker(backend_after_restart, self._sender)

        delivered = worker.run_once()
        replay = TonyPromisedWorkWorker(backend_after_restart, self._sender).run_once()

        self.assertIsNotNone(delivered)
        self.assertEqual(delivered.status.value, "awaiting_approval")
        self.assertEqual(delivered.approval_status, "pending")
        self.assertIsNotNone(workflow_approval_token(delivered))
        self.assertEqual(delivered.promised_work_delivery["status"], "delivered")
        self.assertEqual(len(self.gmail_calls), 1)
        self.assertEqual(len(self.telegram_messages), 1)
        self.assertIn("Gate 2 is ready", self.telegram_messages[0])
        self.assertIsNone(replay)
        persisted = next(item for item in backend_after_restart.list_states() if item.run_id == state.run_id)
        self.assertEqual(persisted.status.value, "awaiting_approval")

    def test_specialist_failure_proactively_reports_blocker_without_duplicate(self) -> None:
        dispatchers = self._dispatchers(fail_specialist=True)
        state, _, _ = self._commission(dispatchers)
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )
        worker = TonyPromisedWorkWorker(backend, self._sender)

        delivered = worker.run_once()
        replay = TonyPromisedWorkWorker(backend, self._sender).run_once()

        self.assertEqual(delivered.status.value, "blocked")
        self.assertIn("couldn’t complete", self.telegram_messages[0])
        self.assertEqual(delivered.promised_work_delivery["status"], "delivered")
        self.assertIsNone(replay)
        self.assertEqual(len(self.telegram_messages), 1)

    def test_ambiguous_telegram_send_is_not_blindly_retried_after_restart(self) -> None:
        _, _, dispatchers = self._commission()
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )
        sends = []

        def uncertain_sender(message: str):
            sends.append(message)
            raise TimeoutError("synthetic send receipt timeout")

        first = TonyPromisedWorkWorker(backend, uncertain_sender).run_once()
        second = TonyPromisedWorkWorker(backend, uncertain_sender).run_once()

        self.assertEqual(first.promised_work_delivery["status"], "attempting")
        self.assertIsNone(second)
        self.assertEqual(len(sends), 1)

    def test_worker_resolves_registered_executive_workspace_to_workflow_tenant(self) -> None:
        runtime_root = self.root / "runtime"
        WorkspaceRuntimeManager(runtime_root, self.root).create(
            "agency",
            "narratiive",
            "Narratiive executive workspace",
        )

        resolved = resolve_workflow_workspace_id(
            {
                "NARRATIIVE_RUNTIME_ROOT": str(runtime_root),
                "TONY_EXECUTIVE_WORKSPACE_ID": "agency",
            }
        )

        self.assertEqual(resolved, "narratiive")


if __name__ == "__main__":
    unittest.main()
