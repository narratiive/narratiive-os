from __future__ import annotations

import tempfile
import unittest
import json
from dataclasses import asdict
from pathlib import Path

from runtime.models import WorkflowState
from runtime.workflow_entity_classification import (
    FileWorkflowEntityClassificationJournal,
    GENUINE_CLIENT,
    INTERNAL_SYNTHETIC_TEST,
    WorkflowEntityClassification,
    WorkflowEntityClassificationService,
)


class WorkflowEntityClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal = FileWorkflowEntityClassificationJournal(
            Path(self.temp.name), authorised_classifier_id="telegram:founder"
        )
        self.state = WorkflowState(
            "growth_diagnostic_to_blueprint_lite", "loom-run", [],
            workspace_id="narratiive", client_id="loom-client", entity_id="inbound-d1b96a67",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _event(self, classification: str, *, supersedes: str = "") -> WorkflowEntityClassification:
        return WorkflowEntityClassification.create(
            workspace_id="narratiive", client_id=self.state.client_id, entity_id="inbound-d1b96a67", workflow_id="growth_diagnostic_to_blueprint_lite",
            classification=classification, classifier_id="telegram:founder",
            authorisation_reference="telegram-message:123", authorisation_turn_id="turn-123",
            authorisation_proof="proof-123", reason="Authorised synthetic test classification.",
            supersedes_event_id=supersedes,
        )

    def test_exact_entity_event_is_append_only_and_replayable(self) -> None:
        event = self.journal.append(
            self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder"
        )

        self.assertEqual(self.journal.classification_for(self.state, states=[self.state]), event)
        self.assertEqual(self.journal.history("narratiive", self.state.entity_id), (event,))

    def test_reclassification_supersedes_without_rewriting_history(self) -> None:
        first = self.journal.append(self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder")
        second = self.journal.append(self._event(GENUINE_CLIENT, supersedes=first.event_id), states=[self.state], principal_id="telegram:founder")

        self.assertEqual(self.journal.history("narratiive", self.state.entity_id), (first, second))
        self.assertEqual(self.journal.classification_for(self.state, states=[self.state]), second)

    def test_cross_workspace_or_unknown_entity_is_rejected(self) -> None:
        foreign = WorkflowEntityClassification.create(
            workspace_id="other", client_id=self.state.client_id, entity_id=self.state.entity_id, workflow_id=self.state.workflow_id,
            classification=INTERNAL_SYNTHETIC_TEST, classifier_id="telegram:founder",
            authorisation_reference="telegram-message:123", authorisation_turn_id="turn-123", authorisation_proof="proof-123", reason="No cross-workspace classification.",
        )
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.journal.append(foreign, states=[self.state], principal_id="telegram:founder")

        unknown = WorkflowEntityClassification.create(
            workspace_id="narratiive", client_id=self.state.client_id, entity_id="other-entity", workflow_id=self.state.workflow_id,
            classification=INTERNAL_SYNTHETIC_TEST, classifier_id="telegram:founder",
            authorisation_reference="telegram-message:123", authorisation_turn_id="turn-123", authorisation_proof="proof-123", reason="No implicit classification.",
        )
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.journal.append(unknown, states=[self.state], principal_id="telegram:founder")

    def test_reclassification_requires_exact_latest_event(self) -> None:
        self.journal.append(self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder")
        with self.assertRaisesRegex(ValueError, "supersession"):
            self.journal.append(self._event(GENUINE_CLIENT, supersedes="wrong"), states=[self.state], principal_id="telegram:founder")

    def test_classification_does_not_cross_client_scope_for_shared_entity_identity(self) -> None:
        event = self.journal.append(
            self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder"
        )
        sibling = WorkflowState(
            self.state.workflow_id, "sibling-run", [], workspace_id="narratiive",
            client_id="other-client", entity_id=self.state.entity_id,
        )
        self.assertEqual(
            self.journal.classification_for(self.state, states=[self.state, sibling]),
            event,
        )
        self.assertIsNone(self.journal.classification_for(sibling, states=[self.state, sibling]))

    def test_legacy_clientless_record_requires_unambiguous_authoritative_client_scope(self) -> None:
        legacy = WorkflowEntityClassification(
            event_id="legacy-event", workspace_id="narratiive", entity_id=self.state.entity_id,
            workflow_id=self.state.workflow_id, classification=INTERNAL_SYNTHETIC_TEST,
            classifier_id="telegram:founder", authorisation_reference="telegram:legacy",
            authorisation_turn_id="turn-legacy", authorisation_proof="proof-legacy",
            reason="Historical authorised classification.", occurred_at="2026-10-30T10:00:00+00:00",
        )
        path = Path(self.temp.name) / "entity-classifications" / "narratiive.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(asdict(legacy)) + "\n")
        sibling = WorkflowState(
            self.state.workflow_id, "sibling-run", [], workspace_id="narratiive",
            client_id="other-client", entity_id=self.state.entity_id,
        )
        self.assertEqual(self.journal.classification_for(self.state, states=[self.state]), legacy)
        self.assertIsNone(self.journal.classification_for(self.state, states=[self.state, sibling]))

    def test_only_the_configured_principal_can_append_a_classification(self) -> None:
        service = WorkflowEntityClassificationService(
            self.journal,
            lambda: (self.state,),
            workspace_id="narratiive",
            authorised_classifier_id="telegram:founder",
        )

        with self.assertRaisesRegex(PermissionError, "authorised classifier"):
            service.record(self._event(INTERNAL_SYNTHETIC_TEST), principal_id="telegram:other")

        recorded = service.record(self._event(INTERNAL_SYNTHETIC_TEST), principal_id="telegram:founder")
        self.assertEqual(
            self.journal.classification_for(self.state, states=[self.state]),
            recorded,
        )

    def test_directly_constructed_or_unauthorised_events_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "classifier_id"):
            WorkflowEntityClassification(
                event_id="event", workspace_id="narratiive", entity_id=self.state.entity_id,
                workflow_id=self.state.workflow_id, classification=INTERNAL_SYNTHETIC_TEST,
                classifier_id="", authorisation_reference="", authorisation_turn_id="", authorisation_proof="", reason="", occurred_at="",
            )
        with self.assertRaisesRegex(PermissionError, "authorised classifier"):
            self.journal.append(
                self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:other"
            )

    def test_missing_authorised_identity_fails_open_to_live_work(self) -> None:
        self.journal.append(
            self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder"
        )
        unavailable_identity_reader = FileWorkflowEntityClassificationJournal(Path(self.temp.name))

        self.assertEqual(unavailable_identity_reader.latest("narratiive"), {})


if __name__ == "__main__":
    unittest.main()
