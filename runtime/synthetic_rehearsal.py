"""Append-only, provider-isolated acceptance evidence for classified test work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from runtime.models import WorkflowState
from runtime.repositories import EventLog, WorkflowEvent
from runtime.workflow_entity_classification import (
    INTERNAL_SYNTHETIC_TEST,
    FileWorkflowEntityClassificationJournal,
)


@dataclass(frozen=True, slots=True)
class SyntheticAcceptance:
    entity_id: str
    proposal_id: str
    proposal_version: str
    proposal_checksum: str
    actor: str
    source_reference: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.entity_id, self.proposal_id, self.proposal_version, self.proposal_checksum, self.actor, self.source_reference)):
            raise ValueError("synthetic acceptance requires exact identity, proposal binding, actor and source")


class SyntheticRehearsalService:
    """Records a test-only commercial handoff without invoking Stripe or providers."""

    def __init__(
        self,
        events: EventLog,
        classifications: FileWorkflowEntityClassificationJournal,
    ) -> None:
        self.events, self.classifications = events, classifications

    def record_acceptance(self, proposal: WorkflowState, acceptance: SyntheticAcceptance) -> tuple[WorkflowEvent, WorkflowEvent]:
        classification = self.classifications.latest(proposal.workspace_id).get(proposal.entity_id)
        if (
            classification is None
            or classification.classification != INTERNAL_SYNTHETIC_TEST
            or classification.workspace_id != proposal.workspace_id
            or classification.workflow_id != proposal.workflow_id
        ):
            raise PermissionError("synthetic acceptance is available only to an authenticated synthetic workflow entity")
        if proposal.entity_id != acceptance.entity_id or proposal.approval_status != "approved":
            raise ValueError("synthetic acceptance requires the exact approved proposal workflow")
        artifact = next((a for stage in proposal.stages for a in stage.output_artifacts if a.artifact_id == acceptance.proposal_id), None)
        if artifact is None or artifact.checksum != acceptance.proposal_checksum:
            raise ValueError("synthetic acceptance proposal binding does not match the persisted artefact")
        payload = {
            "classification": "SYNTHETIC / TEST", "classification_event_id": classification.event_id,
            "provider": "none", "stripe_transaction": None,
            "entity_id": acceptance.entity_id, "proposal_id": acceptance.proposal_id,
            "proposal_version": acceptance.proposal_version, "proposal_checksum": acceptance.proposal_checksum,
            "actor": acceptance.actor, "source_reference": acceptance.source_reference,
        }
        accepted = self._event(proposal, "synthetic_proposal_accepted", payload)
        paid = self._event(proposal, "synthetic_payment_recorded", {**payload, "payment_status": "simulated_paid", "financial_authorisation": False})
        return accepted, paid

    def _event(self, proposal: WorkflowState, event_type: str, payload: dict[str, object]) -> WorkflowEvent:
        payload_digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        digest = hashlib.sha256((event_type + "\0" + proposal.run_id + "\0" + payload_digest).encode()).hexdigest()
        event_id = f"synthetic-{digest[:32]}"
        existing_events = self.events.read(proposal.run_id)
        for existing in existing_events:
            if existing.event_id == event_id:
                return existing
        for existing in existing_events:
            if existing.event_type == event_type:
                raise ValueError("a different synthetic commercial event is already recorded for this proposal")
        event = WorkflowEvent.create(event_id=event_id, run_id=proposal.run_id, event_type=event_type, payload=payload, workspace_id=proposal.workspace_id)
        self.events.append(event)
        return event
