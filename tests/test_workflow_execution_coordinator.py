from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.definitions import (
    ApprovalPolicy,
    InputContract,
    OutputContract,
    RetryPolicy,
    StageDefinition,
    WorkflowDefinition,
)
from runtime.models import StageStatus, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.run_service import WorkflowRunService
from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    WorkerAvailability,
    WorkerMetadata,
    WorkerRegistration,
)
from runtime.workflow_execution_coordinator import (
    FileWorkflowArtifactStore,
    WorkflowExecutionCoordinator,
)
from runtime.workflow_registry import WorkflowRegistry


def _stage(
    stage_id: str,
    *,
    inputs: tuple[str, ...] = ("brief",),
    outputs: tuple[str, ...] = ("draft",),
    quality: str = "quality",
    capability: str = "synthesis",
    attempts: int = 2,
    side_effect: str = "preparation",
    approval_required: bool = False,
) -> StageDefinition:
    return StageDefinition(
        stage_id=stage_id,
        agent_ref="",
        required_inputs=inputs,
        capability=capability,
        input_contract=InputContract(inputs),
        output_contract=OutputContract(outputs),
        quality_contract=quality,
        retry_policy=RetryPolicy(attempts),
        approval_policy=ApprovalPolicy(approval_required, True),
        side_effect_classification=side_effect,
    )


def _lifecycle(
    client_id: str = "client-1",
    stage: ClientLifecycleStage = ClientLifecycleStage.RESEARCH,
    *,
    blocked: bool = False,
) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name="SAFE Synthetic Client",
        stage=stage,
        owner="Tony",
        next_action="Review the proposed next action",
        evidence=("synthetic:test",),
        blocked=blocked,
        blocker="Missing evidence" if blocked else None,
    )


def _worker(adapter, *, capabilities=("synthesis",), side_effects=("preparation",)) -> CapabilityWorkerRegistry:
    return CapabilityWorkerRegistry(
        (
            WorkerRegistration(
                WorkerMetadata(
                    worker_id="test-worker",
                    provider="test",
                    capabilities=capabilities,
                    availability=WorkerAvailability.AVAILABLE,
                    side_effect_permissions=side_effects,
                    max_attempts=1,
                ),
                adapter,
            ),
        )
    )


class WorkflowExecutionCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = FileWorkflowRunRepository(root / "runs", workspace_id="agency", client_id="client-1")
        self.events = JsonlEventLog(root / "events", workspace_id="agency")
        self.runs = WorkflowRunService(
            self.repository,
            self.events,
            workspace_id="agency",
            client_id="client-1",
        )
        self.artifacts = FileWorkflowArtifactStore(root / "artifacts")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _coordinator(self, definition, worker, validators=None):
        return WorkflowExecutionCoordinator(
            registry=WorkflowRegistry((definition,)),
            workers=worker,
            runs=self.runs,
            artifacts=self.artifacts,
            quality_validators=validators or {"quality": lambda output: {"passed": True}},
        )

    def test_autonomous_multi_step_progression_persists_each_output(self) -> None:
        definition = WorkflowDefinition(
            "two-step",
            (
                _stage("draft", outputs=("intermediate",)),
                _stage("finish", inputs=("intermediate",), outputs=("final",)),
            ),
        )

        def adapter(contract):
            if contract["workflow_context"]["stage_id"] == "draft":
                return {"intermediate": "evidence-led draft"}
            self.assertEqual(contract["intermediate"], "evidence-led draft")
            return {"final": "reviewable synthesis"}

        coordinator = self._coordinator(definition, _worker(adapter))
        coordinator.enqueue("two-step", "run-two-step", {"brief": "safe"}, entity_id="entity", correlation_id="corr")
        outcome = coordinator.advance("run-two-step", _lifecycle())
        self.assertEqual(outcome.status, "complete")
        state = self.runs.load_run("run-two-step")
        self.assertEqual([item.status for item in state.stages], [StageStatus.COMPLETED, StageStatus.COMPLETED])
        self.assertEqual(len(state.stages[0].output_artifacts), 1)
        self.assertEqual(state.input_payload["final"], "reviewable synthesis")

    def test_authorised_autonomous_cross_workflow_handoff_is_durable(self) -> None:
        first = WorkflowDefinition(
            "first-workflow",
            (_stage("first", outputs=("handoff",)),),
            next_workflow_id="second-workflow",
            autonomous_handoff=True,
        )
        second = WorkflowDefinition(
            "second-workflow",
            (_stage("second", inputs=("handoff",), outputs=("final",)),),
        )

        def adapter(contract):
            if contract["workflow_context"]["workflow_id"] == "first-workflow":
                return {"handoff": "verified evidence"}
            return {"final": f"used {contract['handoff']}"}

        coordinator = WorkflowExecutionCoordinator(
            registry=WorkflowRegistry((first, second)),
            workers=_worker(adapter),
            runs=self.runs,
            artifacts=self.artifacts,
            quality_validators={"quality": lambda output: {"passed": True}},
        )
        coordinator.enqueue("first-workflow", "run-chain", {"brief": "safe"}, entity_id="e", correlation_id="c")
        outcome = coordinator.advance("run-chain", _lifecycle())
        self.assertEqual(outcome.action, "continue_autonomously")
        self.assertEqual(outcome.next_run_id, "run-chain-second-workflow")
        downstream = self.runs.load_run(outcome.next_run_id)
        self.assertEqual(downstream.status, WorkflowStatus.COMPLETE)
        self.assertEqual(downstream.input_payload["final"], "used verified evidence")

    def test_quality_failure_stops_progression_with_evidence(self) -> None:
        definition = WorkflowDefinition("quality-stop", (_stage("draft"),))
        coordinator = self._coordinator(
            definition,
            _worker(lambda contract: {"draft": "weak"}),
            {"quality": lambda output: {"passed": False, "failed_checks": ["substantive"]}},
        )
        coordinator.enqueue("quality-stop", "run-quality-stop", {"brief": "safe"}, entity_id="e", correlation_id="c")
        outcome = coordinator.advance("run-quality-stop", _lifecycle())
        self.assertEqual(outcome.action, "escalate_blocker")
        state = self.runs.load_run("run-quality-stop")
        self.assertEqual(state.blocker, "quality_failed:quality")
        self.assertEqual(state.stage("draft").quality_result["failed_checks"], ["substantive"])

    def test_present_empty_collection_is_decided_by_quality_contract(self) -> None:
        definition = WorkflowDefinition("empty-collection", (_stage("draft", outputs=("findings",)),))
        coordinator = self._coordinator(
            definition,
            _worker(lambda contract: {"findings": []}),
            {"quality": lambda output: {"passed": False, "failed_checks": ["findings_present"]}},
        )
        coordinator.enqueue("empty-collection", "run-empty", {"brief": "safe"}, entity_id="e", correlation_id="c")

        outcome = coordinator.advance("run-empty", _lifecycle())

        self.assertEqual(outcome.blocker, "quality_failed:quality")
        self.assertEqual(self.runs.load_run("run-empty").stage("draft").quality_result["failed_checks"], ["findings_present"])

    def test_worker_unavailable_becomes_explicit_blocker(self) -> None:
        definition = WorkflowDefinition("no-worker", (_stage("draft", capability="market_research"),))
        coordinator = self._coordinator(definition, CapabilityWorkerRegistry())
        coordinator.enqueue("no-worker", "run-no-worker", {"brief": "safe"}, entity_id="e", correlation_id="c")
        outcome = coordinator.advance("run-no-worker", _lifecycle())
        self.assertEqual(outcome.blocker, "worker_unavailable:market_research")
        self.assertFalse(outcome.external_action_taken)

    def test_human_gate_pauses_before_worker_execution(self) -> None:
        calls = []
        definition = WorkflowDefinition("approval-pause", (_stage("draft"),))
        coordinator = self._coordinator(definition, _worker(lambda contract: calls.append(contract) or {"draft": "x"}))
        coordinator.enqueue("approval-pause", "run-pause", {"brief": "safe"}, entity_id="e", correlation_id="c")
        outcome = coordinator.advance("run-pause", _lifecycle(stage=ClientLifecycleStage.OUTREACH))
        self.assertEqual(outcome.action, "await_human_approval")
        self.assertEqual(calls, [])
        self.assertEqual(self.runs.load_run("run-pause").approval_status, "pending")

    def test_explicit_approval_resumes_the_exact_persisted_action(self) -> None:
        calls = []
        definition = WorkflowDefinition("approval-resume", (_stage("draft"),))
        coordinator = self._coordinator(definition, _worker(lambda contract: calls.append(contract) or {"draft": "ready"}))
        coordinator.enqueue("approval-resume", "run-resume", {"brief": "safe"}, entity_id="e", correlation_id="c")
        lifecycle = _lifecycle(stage=ClientLifecycleStage.OUTREACH)
        coordinator.advance("run-resume", lifecycle)
        coordinator.approve("run-resume", approver="authorised-human", rationale="Safe test approval")
        outcome = coordinator.advance("run-resume", lifecycle)
        self.assertEqual(outcome.status, "complete")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.runs.load_run("run-resume").approval_history), 1)

    def test_restart_recovers_pending_work_without_duplicate_execution(self) -> None:
        calls = []
        definition = WorkflowDefinition("restart-safe", (_stage("draft"),))
        workers = _worker(lambda contract: calls.append(contract) or {"draft": "durable"})
        first = self._coordinator(definition, workers)
        first.enqueue("restart-safe", "run-restart", {"brief": "safe"}, entity_id="e", correlation_id="c")
        restarted_runs = WorkflowRunService(self.repository, self.events, workspace_id="agency", client_id="client-1")
        restarted = WorkflowExecutionCoordinator(
            registry=WorkflowRegistry((definition,)),
            workers=workers,
            runs=restarted_runs,
            artifacts=self.artifacts,
            quality_validators={"quality": lambda output: {"passed": True}},
        )
        self.assertEqual(restarted.advance("run-restart", _lifecycle()).status, "complete")
        self.assertEqual(restarted.advance("run-restart", _lifecycle()).status, "complete")
        self.assertEqual(len(calls), 1)

    def test_duplicate_inbound_event_is_idempotent(self) -> None:
        calls = []
        definition = WorkflowDefinition("inbound-idempotent", (_stage("draft"),))
        coordinator = self._coordinator(definition, _worker(lambda contract: calls.append(contract) or {"draft": "once"}))
        first = coordinator.enqueue("inbound-idempotent", "same-event", {"brief": "safe"}, entity_id="e", correlation_id="c")
        replay = coordinator.enqueue("inbound-idempotent", "same-event", {"brief": "safe"}, entity_id="e", correlation_id="c")
        self.assertEqual(first.run_id, replay.run_id)
        coordinator.advance("same-event", _lifecycle())
        coordinator.advance("same-event", _lifecycle())
        coordinator.enqueue(
            "inbound-idempotent",
            "same-event",
            {"brief": "safe"},
            entity_id="e",
            correlation_id="c",
        )
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(ValueError, "different inputs"):
            coordinator.enqueue(
                "inbound-idempotent",
                "same-event",
                {"brief": "changed"},
                entity_id="e",
                correlation_id="c",
            )

    def test_concurrent_advance_leases_one_execution(self) -> None:
        calls = []
        definition = WorkflowDefinition("concurrent-safe", (_stage("draft"),))
        coordinator = self._coordinator(
            definition,
            _worker(lambda contract: calls.append(contract) or {"draft": "once"}),
        )
        coordinator.enqueue("concurrent-safe", "run-concurrent", {"brief": "safe"}, entity_id="e", correlation_id="c")
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: coordinator.advance("run-concurrent", _lifecycle()), range(2)))
        self.assertEqual([item.status for item in outcomes], ["complete", "complete"])
        self.assertEqual(len(calls), 1)

    def test_prohibited_external_action_claim_is_blocked(self) -> None:
        definition = WorkflowDefinition("false-execution", (_stage("draft"),))
        coordinator = self._coordinator(
            definition,
            _worker(lambda contract: {"draft": "prepared", "external_action_taken": True}),
        )
        coordinator.enqueue("false-execution", "run-false", {"brief": "safe"}, entity_id="e", correlation_id="c")
        outcome = coordinator.advance("run-false", _lifecycle())
        self.assertIn("ProhibitedWorkerSideEffect", outcome.blocker)
        self.assertFalse(self.runs.load_run("run-false").external_action_taken)

    def test_external_write_requires_approval_receipt_and_is_not_replayed(self) -> None:
        calls = []
        definition = WorkflowDefinition(
            "approved-external",
            (
                _stage(
                    "send",
                    outputs=("external_action_receipt",),
                    capability="email_sending",
                    side_effect="external_write",
                    approval_required=True,
                ),
            ),
        )

        def adapter(contract):
            calls.append(contract["workflow_context"]["idempotency_key"])
            return {
                "external_action_taken": True,
                "external_action_receipt": {"provider_id": "synthetic-receipt"},
            }

        coordinator = self._coordinator(
            definition,
            _worker(adapter, capabilities=("email_sending",), side_effects=("external_write",)),
        )
        coordinator.enqueue("approved-external", "run-write", {"brief": "safe"}, entity_id="e", correlation_id="c")
        paused = coordinator.advance("run-write", _lifecycle())
        self.assertEqual(paused.action, "await_human_approval")
        self.assertEqual(calls, [])
        coordinator.approve("run-write", approver="authorised-human", rationale="Synthetic adapter test")
        completed = coordinator.advance("run-write", _lifecycle())
        self.assertEqual(completed.status, "complete")
        self.assertTrue(completed.external_action_taken)
        self.assertEqual(len(calls), 1)
        coordinator.advance("run-write", _lifecycle())
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.runs.load_run("run-write").external_action_receipts), 1)


if __name__ == "__main__":
    unittest.main()
