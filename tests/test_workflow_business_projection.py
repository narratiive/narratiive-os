from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.models import StageRecord, WorkflowState, WorkflowStatus
from runtime.workflow_business_projection import WorkflowBusinessProjectionService


def state(*, status: WorkflowStatus = WorkflowStatus.AWAITING_APPROVAL) -> WorkflowState:
    return WorkflowState(
        workflow_id="blueprint_lite_to_discovery_preparation",
        run_id="safe-projection-run",
        stages=[StageRecord("prepare_discovery", "Claude")],
        status=status,
        current_stage_id="prepare_discovery",
        approval_required=True,
        workspace_id="agency",
        client_id="safe-client",
        entity_id="safe-lead",
        correlation_id="safe-correlation",
        proposed_next_action="Approve internal discovery preparation.",
        approval_status="pending",
    )


class WorkflowBusinessProjectionTests(unittest.TestCase):
    def test_prepare_is_local_append_only_and_reports_runtime_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = WorkflowBusinessProjectionService(tmp)
            current = state()

            first = service.prepare(current)
            second = service.prepare(current)

            self.assertEqual(first["projection_key"], second["projection_key"])
            self.assertEqual(first["lifecycle_stage"], "discovery")
            self.assertTrue(first["outstanding_approval"])
            self.assertEqual(first["projection_status"], "prepared")
            events = Path(tmp, "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 1)

    def test_explicit_sync_is_verified_and_replay_is_suppressed_after_restart(self) -> None:
        calls = []

        def notion(dispatch):
            calls.append(dispatch)
            return {
                "external_action_taken": True,
                "record_id": "safe-notion-record",
                "projection_key": dispatch["idempotency_key"],
            }

        with tempfile.TemporaryDirectory() as tmp:
            service = WorkflowBusinessProjectionService(tmp, notion)
            current = state()
            first = service.sync(current, approver="telegram:123", rationale="SAFE projection test")
            restarted = WorkflowBusinessProjectionService(tmp, notion)
            replay = restarted.sync(current, approver="telegram:123", rationale="SAFE replay test")

            self.assertEqual(first["projection_status"], "verified")
            self.assertTrue(first["external_action_taken"])
            self.assertEqual(replay["projection_status"], "duplicate_suppressed")
            self.assertFalse(replay["external_action_taken"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["payload"]["kind"], "workflow_business_state_projection")
            self.assertEqual(calls[0]["execution_mode"], "approval_gated_write")

    def test_ambiguous_dispatch_requires_reconciliation_not_blind_retry(self) -> None:
        calls = []

        def unverified(dispatch):
            calls.append(dispatch)
            return {"external_action_taken": True, "record_id": "record-without-key"}

        with tempfile.TemporaryDirectory() as tmp:
            service = WorkflowBusinessProjectionService(tmp, unverified)
            current = state()
            first = service.sync(current, approver="telegram:123", rationale="SAFE projection test")
            retry = service.sync(current, approver="telegram:123", rationale="SAFE retry test")
            reconciled = service.reconcile(
                current,
                {"record_id": "safe-notion-record", "projection_key": first["projection_key"]},
            )

            self.assertEqual(first["projection_status"], "reconciliation_required")
            self.assertEqual(retry["projection_status"], "reconciliation_required")
            self.assertEqual(len(calls), 1)
            self.assertEqual(reconciled["projection_status"], "reconciled")
            self.assertFalse(reconciled["external_action_taken"])

    def test_missing_dispatcher_does_not_consume_future_idempotent_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            unavailable = WorkflowBusinessProjectionService(tmp)
            current = state()
            blocked = unavailable.sync(current, approver="telegram:123", rationale="SAFE projection test")
            configured = WorkflowBusinessProjectionService(
                tmp,
                lambda dispatch: {
                    "external_action_taken": True,
                    "record_id": "safe-notion-record",
                    "projection_key": dispatch["idempotency_key"],
                },
            )
            completed = configured.sync(current, approver="telegram:123", rationale="SAFE configured retry")

            self.assertEqual(blocked["projection_status"], "notion_dispatcher_unavailable")
            self.assertEqual(completed["projection_status"], "verified")


if __name__ == "__main__":
    unittest.main()
