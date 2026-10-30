from __future__ import annotations

import tempfile
import unittest
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
            workspace_id="narratiive", entity_id="inbound-d1b96a67", workflow_id="growth_diagnostic_to_blueprint_lite",
            classification=classification, classifier_id="telegram:founder",
            authorisation_reference="telegram-message:123", reason="Authorised synthetic test classification.",
            supersedes_event_id=supersedes,
        )

    def test_exact_entity_event_is_append_only_and_replayable(self) -> None:
        event = self.journal.append(
            self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder"
        )

        self.assertEqual(self.journal.latest("narratiive")[self.state.entity_id], event)
        self.assertEqual(self.journal.history("narratiive", self.state.entity_id), (event,))

    def test_reclassification_supersedes_without_rewriting_history(self) -> None:
        first = self.journal.append(self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder")
        second = self.journal.append(self._event(GENUINE_CLIENT, supersedes=first.event_id), states=[self.state], principal_id="telegram:founder")

        self.assertEqual(self.journal.history("narratiive", self.state.entity_id), (first, second))
        self.assertEqual(self.journal.latest("narratiive")[self.state.entity_id], second)

    def test_cross_workspace_or_unknown_entity_is_rejected(self) -> None:
        foreign = WorkflowEntityClassification.create(
            workspace_id="other", entity_id=self.state.entity_id, workflow_id=self.state.workflow_id,
            classification=INTERNAL_SYNTHETIC_TEST, classifier_id="telegram:founder",
            authorisation_reference="telegram-message:123", reason="No cross-workspace classification.",
        )
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.journal.append(foreign, states=[self.state], principal_id="telegram:founder")

        unknown = WorkflowEntityClassification.create(
            workspace_id="narratiive", entity_id="other-entity", workflow_id=self.state.workflow_id,
            classification=INTERNAL_SYNTHETIC_TEST, classifier_id="telegram:founder",
            authorisation_reference="telegram-message:123", reason="No implicit classification.",
        )
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.journal.append(unknown, states=[self.state], principal_id="telegram:founder")

    def test_reclassification_requires_exact_latest_event(self) -> None:
        self.journal.append(self._event(INTERNAL_SYNTHETIC_TEST), states=[self.state], principal_id="telegram:founder")
        with self.assertRaisesRegex(ValueError, "supersession"):
            self.journal.append(self._event(GENUINE_CLIENT, supersedes="wrong"), states=[self.state], principal_id="telegram:founder")

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
        self.assertEqual(self.journal.latest("narratiive")[self.state.entity_id], recorded)

    def test_directly_constructed_or_unauthorised_events_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "classifier_id"):
            WorkflowEntityClassification(
                event_id="event", workspace_id="narratiive", entity_id=self.state.entity_id,
                workflow_id=self.state.workflow_id, classification=INTERNAL_SYNTHETIC_TEST,
                classifier_id="", authorisation_reference="", reason="", occurred_at="",
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
