from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_internal_review_delivery import workflow_approval_token
from runtime.tony_promised_work import TonyPromisedWorkWorker
from runtime.tony_workflow_commands import FileWorkflowCommandBackend
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from runtime.run_service import resolve_notion_record_identity
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


from tests.fieldwork_test_support import lifecycle_pdf_fixture


@lifecycle_pdf_fixture
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

    def _commission(self, dispatchers=None, *, notion_identity=None):
        dispatchers = dispatchers or self._dispatchers()
        notion_identity = notion_identity or {
            "notion_page_id": "40d0c9cf-a8f2-810f-b599-d478255f11e4",
        }
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
            {
                "diagnostic_input_package": {"overall_score": 42},
                "company": "SAFE Promised Work Company",
                **notion_identity,
            },
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
        self.assertNotIn("evidence_lineage", state.input_payload)
        self.assertEqual(
            state.input_payload["notion_page_id"],
            "40d0c9cf-a8f2-810f-b599-d478255f11e4",
        )
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
        self.assertIn("Fieldwork proposal is ready", self.telegram_messages[0])
        self.assertLess(len(self.telegram_messages[0]), 900)
        attachment = self.gmail_calls[0]["payload"]["attachments"][0]
        self.assertEqual(attachment["mime_type"], "application/pdf")
        self.assertTrue(attachment["filename"].endswith(".pdf"))
        self.assertLess(len(self.gmail_calls[0]["payload"]["body"]), 3000)
        self.assertIn("CLIENT EMAIL DRAFT — NOT SENT", self.gmail_calls[0]["payload"]["body"])
        self.assertIn("PDF SHA-256:", self.gmail_calls[0]["payload"]["body"])
        self.assertIn("Review copy: https://mail.google.com/", self.telegram_messages[0])
        visible = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(io.BytesIO(base64.b64decode(attachment["content_base64"]))).pages
        )
        self.assertIn("FIELDWORK PROPOSAL", visible)
        self.assertIn("THE MARKETING OPPORTUNITY", visible)
        self.assertIn("THREE OUTPUTS", visible)
        for internal in (
            "provider_message_id", "worker_execution", "selection_reason",
            "source_refs", "artifact-", "safe-promised-source",
        ):
            self.assertNotIn(internal, visible)
        self.assertIsNone(replay)
        persisted = next(item for item in backend_after_restart.list_states() if item.run_id == state.run_id)
        self.assertEqual(persisted.status.value, "awaiting_approval")

    def test_promised_worker_does_not_readvance_an_already_running_canonical_stage(self) -> None:
        state, _, dispatchers = self._commission()
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        runtime.runs.start_stage(state.run_id, state.current_stage_id)
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )

        observed = TonyPromisedWorkWorker(backend, self._sender).run_once()

        self.assertEqual(observed.run_id, state.run_id)
        self.assertEqual(observed.status.value, "active")
        self.assertEqual(observed.stage(observed.current_stage_id).status.value, "running")
        self.assertIsNone(observed.blocker)
        self.assertEqual(self.telegram_messages, [])

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
        self.assertIn("FIELDWORK proposal is paused", self.telegram_messages[0])
        self.assertIn("engineering check", self.telegram_messages[0])
        self.assertNotIn("RuntimeError", self.telegram_messages[0])
        self.assertNotIn("quality_failed", self.telegram_messages[0])
        self.assertEqual(delivered.promised_work_delivery["status"], "delivered")
        self.assertIsNone(replay)
        self.assertEqual(len(self.telegram_messages), 1)

    def test_recovered_gate_notification_supersedes_delivered_worker_failure_once(self) -> None:
        state, _, dispatchers = self._commission()
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        failed_key = "safe-worker-failure-delivery"
        runtime.runs.begin_promised_delivery(
            state.run_id,
            delivery_key=failed_key,
            kind="worker_failure",
        )
        runtime.runs.finish_promised_delivery(
            state.run_id,
            delivery_key=failed_key,
            evidence={"provider": "telegram", "message_id": "failure-1"},
        )
        runtime.advance(state.run_id, lifecycle())
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )

        delivered = TonyPromisedWorkWorker(backend, self._sender).run_once()
        replay = TonyPromisedWorkWorker(backend, self._sender).run_once()

        self.assertEqual(delivered.status.value, "awaiting_approval")
        self.assertEqual(delivered.promised_work_delivery["kind"], "gate_ready")
        self.assertEqual(delivered.promised_work_delivery["supersedes_delivery_key"], failed_key)
        self.assertEqual(delivered.promised_work_delivery["supersedes_kind"], "worker_failure")
        self.assertIsNone(replay)
        self.assertEqual(len(self.gmail_calls), 1)
        self.assertEqual(len(self.telegram_messages), 1)

    def test_worker_retries_quality_passed_persistence_failure_and_recovers_without_reexecution(self) -> None:
        specialist_calls = []

        def claude(contract):
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                specialist_calls.append("proposal")
                return proposal_output()
            return blueprint_output()

        dispatchers = self._dispatchers()
        dispatchers["Claude"] = claude
        state, _, _ = self._commission(dispatchers)
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        # Reproduce the persisted legacy commission shape that caused the live
        # Origin proposal's accepted evidence_lineage output to collide.
        interrupted_input = runtime.runs.load_run(state.run_id)
        interrupted_input.input_payload["evidence_lineage"] = ["inherited-discovery-evidence"]
        runtime.runs.repository.save(interrupted_input)
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )

        failed = TonyPromisedWorkWorker(backend, self._sender).run_once()
        recovered = TonyPromisedWorkWorker(backend, self._sender).run_once()
        replay = TonyPromisedWorkWorker(backend, self._sender).run_once()

        self.assertEqual(failed.status.value, "active")
        self.assertEqual(failed.promised_work_delivery["kind"], "worker_failure")
        self.assertEqual(recovered.status.value, "awaiting_approval")
        self.assertEqual(recovered.promised_work_delivery["kind"], "gate_ready")
        self.assertEqual(
            recovered.promised_work_delivery["supersedes_kind"],
            "worker_failure",
        )
        self.assertEqual(specialist_calls, ["proposal"])
        self.assertEqual(
            len(recovered.stage("prepare_growth_sprint_proposal").output_artifacts),
            1,
        )
        self.assertEqual(len(self.gmail_calls), 1)
        self.assertEqual(len(self.telegram_messages), 2)
        self.assertIsNone(replay)

    def test_restart_recovery_keeps_quality_passed_orphan_eligible_without_reexecution(self) -> None:
        specialist_calls = []

        def claude(contract):
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                specialist_calls.append("proposal")
                return proposal_output()
            return blueprint_output()

        dispatchers = self._dispatchers()
        dispatchers["Claude"] = claude
        state, _, _ = self._commission(dispatchers)
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        interrupted_input = runtime.runs.load_run(state.run_id)
        interrupted_input.input_payload["evidence_lineage"] = ["inherited-discovery-evidence"]
        runtime.runs.repository.save(interrupted_input)
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )

        failed = TonyPromisedWorkWorker(backend, self._sender).run_once()
        recovered_count = runtime.coordinator.recover_pending()
        after_restart = runtime.runs.load_run(state.run_id)
        self.assertTrue(TonyPromisedWorkWorker._quality_passed_recovery_pending(after_restart))
        recovered = TonyPromisedWorkWorker(backend, self._sender).run_once()

        self.assertEqual(failed.promised_work_delivery["kind"], "worker_failure")
        self.assertEqual(recovered_count, 1)
        self.assertEqual(
            after_restart.stage("prepare_growth_sprint_proposal").status.value,
            "ready",
        )
        self.assertEqual(recovered.status.value, "awaiting_approval")
        self.assertEqual(recovered.promised_work_delivery["kind"], "gate_ready")
        self.assertEqual(specialist_calls, ["proposal"])
        self.assertEqual(
            len(recovered.stage("prepare_growth_sprint_proposal").output_artifacts),
            1,
        )

    def test_tampered_recovery_does_not_resend_delivered_worker_failure(self) -> None:
        state, _, dispatchers = self._commission()
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        interrupted_input = runtime.runs.load_run(state.run_id)
        interrupted_input.input_payload["evidence_lineage"] = ["inherited-discovery-evidence"]
        runtime.runs.repository.save(interrupted_input)
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )
        worker = TonyPromisedWorkWorker(backend, self._sender)

        first = worker.run_once()
        orphan = next(self.root.rglob("artifact-*.json"))
        orphan.write_text("{}\n", encoding="utf-8")
        second = worker.run_once()
        third = worker.run_once()

        self.assertEqual(first.promised_work_delivery["kind"], "worker_failure")
        self.assertEqual(second.status.value, "active")
        self.assertEqual(third.status.value, "active")
        self.assertEqual(len(self.telegram_messages), 1)

    def test_ambiguous_recovery_does_not_resend_delivered_worker_failure(self) -> None:
        state, _, dispatchers = self._commission()
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        interrupted_input = runtime.runs.load_run(state.run_id)
        interrupted_input.input_payload["evidence_lineage"] = ["inherited-discovery-evidence"]
        runtime.runs.repository.save(interrupted_input)
        backend = FileWorkflowCommandBackend(
            self.root,
            dispatchers=dispatchers,
            environ={},
            workspace_id="narratiive",
        )
        worker = TonyPromisedWorkWorker(backend, self._sender)

        first = worker.run_once()
        orphan = next(self.root.rglob("artifact-*.json"))
        identity = orphan.stem.split("-")[1]
        duplicate = orphan.with_name(f"artifact-{identity}-0000000000000000.json")
        duplicate.write_bytes(orphan.read_bytes())
        second = worker.run_once()
        third = worker.run_once()

        self.assertEqual(first.promised_work_delivery["kind"], "worker_failure")
        self.assertEqual(second.status.value, "active")
        self.assertEqual(third.status.value, "active")
        self.assertEqual(len(self.telegram_messages), 1)

    def test_projection_inherits_existing_parent_notion_identity_for_legacy_commission(self) -> None:
        notion_calls = []

        def notion(contract):
            notion_calls.append(contract)
            return {
                "external_action_taken": True,
                "record_id": "40d0c9cf-a8f2-810f-b599-d478255f11e4",
                "projection_key": contract["idempotency_key"],
            }

        dispatchers = self._dispatchers()
        dispatchers["Notion"] = notion
        state, _, _ = self._commission(dispatchers)
        runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-client",
            dispatchers=dispatchers,
            environ={},
        )
        legacy = runtime.runs.load_run(state.run_id)
        legacy.input_payload.pop("notion_page_id")
        runtime.runs.repository.save(legacy)

        synced = runtime.sync_business_projection(
            state.run_id,
            approver="telegram:matt",
            rationale="Reconcile the exact inherited Notion record identity.",
        )
        persisted = runtime.runs.load_run(state.run_id)
        events = runtime.runs.event_log.read(state.run_id)
        replay = runtime.sync_business_projection(
            state.run_id,
            approver="telegram:matt",
            rationale="Verify the inherited Notion projection is idempotent.",
        )

        self.assertEqual(synced["projection_status"], "verified")
        self.assertEqual(replay["projection_status"], "duplicate_suppressed")
        self.assertEqual(
            persisted.input_payload["notion_page_id"],
            "40d0c9cf-a8f2-810f-b599-d478255f11e4",
        )
        self.assertEqual(len(notion_calls), 1)
        self.assertEqual(
            sum(event.event_type == "workflow.notion_identity_inherited" for event in events),
            1,
        )

    def test_commission_rejects_conflicting_or_malformed_parent_notion_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid or conflicting Notion"):
            self._commission(
                notion_identity={
                    "notion_page_id": "40d0c9cf-a8f2-810f-b599-d478255f11e4",
                    "notion_record_id": "50d0c9cf-a8f2-810f-b599-d478255f11e5",
                }
            )

        with self.assertRaisesRegex(ValueError, "invalid or conflicting Notion"):
            resolve_notion_record_identity({"notion_page_id": "not-a-provider-page-id"})

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
