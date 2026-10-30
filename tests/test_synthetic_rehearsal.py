import tempfile
import threading
import unittest
from pathlib import Path

from runtime.models import ArtifactRef, StageRecord, WorkflowState, WorkflowStatus
from runtime.repositories import JsonlEventLog
from runtime.synthetic_rehearsal import SyntheticAcceptance, SyntheticRehearsalService
from runtime.workflow_entity_classification import (
    INTERNAL_SYNTHETIC_TEST,
    FileWorkflowEntityClassificationJournal,
    WorkflowEntityClassification,
)


class SyntheticRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        artifact = ArtifactRef(
            "proposal-v3", "workflow_step_output", "/safe/proposal.json", "checksum-v3",
            metadata={"version": 3},
        )
        self.proposal = WorkflowState("discovery_evidence_to_growth_sprint_proposal", "loom-proposal-v3", [StageRecord("draft", "Claude", output_artifacts=[artifact])], status=WorkflowStatus.COMPLETE, approval_required=True, approval_status="approved", workspace_id="narratiive", client_id="loom", entity_id="inbound-d1b96a67")
        self.classifier_id = "telegram:founder"
        self.proposal.approval_history.append({
            "approver": self.classifier_id,
            "approved_at": "2026-10-30T10:45:26+00:00",
            "approval_binding": {
                "approval_binding_digest": "approval-binding",
                "workflow_id": self.proposal.workflow_id,
                "run_id": self.proposal.run_id,
                "artifact_id": artifact.artifact_id,
                "artifact_checksum": artifact.checksum,
                "artifact_version": "v3",
                "human_decision": {
                    "explicit_decision_intent": "approve",
                    "verbatim_current_human_instruction_verified": True,
                },
            },
        })
        event = WorkflowEntityClassification.create(workspace_id="narratiive", client_id="loom", run_id=self.proposal.run_id, entity_id="inbound-d1b96a67", workflow_id=self.proposal.workflow_id, classification=INTERNAL_SYNTHETIC_TEST, classifier_id=self.classifier_id, authorisation_reference="telegram:1", authorisation_turn_id="turn-1", authorisation_proof="proof", reason="test")
        self.events = JsonlEventLog(Path(self.tmp.name), workspace_id="narratiive")
        self.classifications = FileWorkflowEntityClassificationJournal(
            Path(self.tmp.name), authorised_classifier_id=self.classifier_id,
        )
        self.classifications.append(event, states=[self.proposal], principal_id=self.classifier_id)
        self.service = SyntheticRehearsalService(
            self.events, self.classifications, self._load_state, self._load_states,
        )
        self.acceptance = SyntheticAcceptance("inbound-d1b96a67", "proposal-v3", "v3", "checksum-v3", self.classifier_id, "test-directive:loom")

    def _load_state(self, workspace_id, client_id, run_id):
        if (workspace_id, client_id, run_id) != (
            self.proposal.workspace_id, self.proposal.client_id, self.proposal.run_id,
        ):
            raise KeyError(run_id)
        return self.proposal

    def _load_states(self, workspace_id):
        if workspace_id != self.proposal.workspace_id:
            return ()
        return (self.proposal,)

    def test_records_distinct_idempotent_test_acceptance_and_payment(self):
        first = self.service.record_acceptance(self.proposal, self.acceptance)
        second = self.service.record_acceptance(self.proposal, self.acceptance)
        self.assertEqual([item.event_id for item in first], [item.event_id for item in second])
        events = self.events.read(self.proposal.run_id)
        self.assertEqual([item.event_type for item in events], ["synthetic_proposal_accepted", "synthetic_payment_recorded"])
        self.assertTrue(all(item.payload["classification"] == "SYNTHETIC / TEST" for item in events))
        self.assertTrue(all(item.payload["provider"] == "none" for item in events))
        self.assertTrue(all(item.payload["client_id"] == "loom" for item in events))
        self.assertTrue(all(item.payload["approval_binding_digest"] == "approval-binding" for item in events))

    def test_rejects_non_synthetic_or_changed_proposal(self):
        self.service = SyntheticRehearsalService(
            self.events,
            FileWorkflowEntityClassificationJournal(
                Path(self.tmp.name) / "unclassified", authorised_classifier_id=self.classifier_id,
            ),
            self._load_state,
            self._load_states,
        )
        with self.assertRaises(PermissionError): self.service.record_acceptance(self.proposal, self.acceptance)
        changed = SyntheticAcceptance("inbound-d1b96a67", "proposal-v3", "v3", "other", "founder:synthetic-rehearsal", "test-directive:loom")
        service = SyntheticRehearsalService(
            self.events, self.classifications, self._load_state, self._load_states,
        )
        with self.assertRaises(ValueError): service.record_acceptance(self.proposal, changed)

    def test_rejects_conflicting_replay_after_the_exact_test_event(self):
        self.service.record_acceptance(self.proposal, self.acceptance)
        changed = SyntheticAcceptance(
            "inbound-d1b96a67", "proposal-v3", "v3", "checksum-v3",
            self.classifier_id, "different-test-directive",
        )
        with self.assertRaisesRegex(ValueError, "different synthetic commercial event"):
            self.service.record_acceptance(self.proposal, changed)

    def test_rejects_mismatched_version_or_unbound_approval(self):
        wrong_version = SyntheticAcceptance(
            "inbound-d1b96a67", "proposal-v3", "v2", "checksum-v3", self.classifier_id, "test-directive:loom",
        )
        with self.assertRaises(ValueError):
            self.service.record_acceptance(self.proposal, wrong_version)
        self.proposal.approval_history.clear()
        with self.assertRaises(PermissionError):
            self.service.record_acceptance(self.proposal, self.acceptance)

    def test_rejects_non_approval_human_decision(self):
        self.proposal.approval_history[-1]["approval_binding"]["human_decision"]["explicit_decision_intent"] = "request_revision"
        with self.assertRaises(PermissionError):
            self.service.record_acceptance(self.proposal, self.acceptance)

    def test_concurrent_replay_writes_each_synthetic_event_once(self):
        barrier = threading.Barrier(2)
        errors = []

        def record():
            try:
                barrier.wait()
                self.service.record_acceptance(self.proposal, self.acceptance)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        first = threading.Thread(target=record)
        second = threading.Thread(target=record)
        first.start(); second.start(); first.join(); second.join()
        self.assertEqual(errors, [])
        events = self.events.read(self.proposal.run_id)
        self.assertEqual(
            [item.event_type for item in events],
            ["synthetic_proposal_accepted", "synthetic_payment_recorded"],
        )
