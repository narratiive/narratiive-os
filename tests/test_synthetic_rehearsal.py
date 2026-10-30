import tempfile
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
        artifact = ArtifactRef("proposal-v3", "workflow_step_output", "/safe/proposal.json", "checksum-v3")
        self.proposal = WorkflowState("discovery_evidence_to_growth_sprint_proposal", "loom-proposal-v3", [StageRecord("draft", "Claude", output_artifacts=[artifact])], status=WorkflowStatus.COMPLETE, approval_required=True, approval_status="approved", workspace_id="narratiive", client_id="loom", entity_id="inbound-d1b96a67")
        self.classifier_id = "telegram:founder"
        event = WorkflowEntityClassification.create(workspace_id="narratiive", entity_id="inbound-d1b96a67", workflow_id=self.proposal.workflow_id, classification=INTERNAL_SYNTHETIC_TEST, classifier_id=self.classifier_id, authorisation_reference="telegram:1", authorisation_turn_id="turn-1", authorisation_proof="proof", reason="test")
        self.events = JsonlEventLog(Path(self.tmp.name), workspace_id="narratiive")
        self.classifications = FileWorkflowEntityClassificationJournal(
            Path(self.tmp.name), authorised_classifier_id=self.classifier_id,
        )
        self.classifications.append(event, states=[self.proposal], principal_id=self.classifier_id)
        self.service = SyntheticRehearsalService(self.events, self.classifications)
        self.acceptance = SyntheticAcceptance("inbound-d1b96a67", "proposal-v3", "v3", "checksum-v3", "founder:synthetic-rehearsal", "test-directive:loom")

    def test_records_distinct_idempotent_test_acceptance_and_payment(self):
        first = self.service.record_acceptance(self.proposal, self.acceptance)
        second = self.service.record_acceptance(self.proposal, self.acceptance)
        self.assertEqual([item.event_id for item in first], [item.event_id for item in second])
        events = self.events.read(self.proposal.run_id)
        self.assertEqual([item.event_type for item in events], ["synthetic_proposal_accepted", "synthetic_payment_recorded"])
        self.assertTrue(all(item.payload["classification"] == "SYNTHETIC / TEST" for item in events))
        self.assertTrue(all(item.payload["provider"] == "none" for item in events))

    def test_rejects_non_synthetic_or_changed_proposal(self):
        self.service = SyntheticRehearsalService(
            self.events,
            FileWorkflowEntityClassificationJournal(
                Path(self.tmp.name) / "unclassified", authorised_classifier_id=self.classifier_id,
            ),
        )
        with self.assertRaises(PermissionError): self.service.record_acceptance(self.proposal, self.acceptance)
        changed = SyntheticAcceptance("inbound-d1b96a67", "proposal-v3", "v3", "other", "founder:synthetic-rehearsal", "test-directive:loom")
        service = SyntheticRehearsalService(self.events, self.classifications)
        with self.assertRaises(ValueError): service.record_acceptance(self.proposal, changed)

    def test_rejects_conflicting_replay_after_the_exact_test_event(self):
        self.service.record_acceptance(self.proposal, self.acceptance)
        changed = SyntheticAcceptance(
            "inbound-d1b96a67", "proposal-v3", "v3", "checksum-v3",
            "founder:synthetic-rehearsal", "different-test-directive",
        )
        with self.assertRaisesRegex(ValueError, "different synthetic commercial event"):
            self.service.record_acceptance(self.proposal, changed)
