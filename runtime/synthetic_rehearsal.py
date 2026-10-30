"""Append-only, provider-isolated acceptance evidence for classified test work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

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
        state_loader: Callable[[str, str, str], WorkflowState],
        states_loader: Callable[[str], tuple[WorkflowState, ...]],
    ) -> None:
        self.events = events
        self.classifications = classifications
        self.state_loader = state_loader
        self.states_loader = states_loader

    def record_acceptance(self, proposal: WorkflowState, acceptance: SyntheticAcceptance) -> tuple[WorkflowEvent, WorkflowEvent]:
        canonical = self.state_loader(
            proposal.workspace_id,
            proposal.client_id,
            proposal.run_id,
        )
        if (
            canonical.workspace_id != proposal.workspace_id
            or canonical.client_id != proposal.client_id
            or canonical.entity_id != proposal.entity_id
            or canonical.workflow_id != proposal.workflow_id
            or canonical.run_id != proposal.run_id
        ):
            raise PermissionError("synthetic acceptance state does not match the authoritative scoped run")
        classification = self.classifications.classification_for(
            canonical, states=self.states_loader(canonical.workspace_id)
        )
        if (
            classification is None
            or classification.classification != INTERNAL_SYNTHETIC_TEST
            or classification.workspace_id != canonical.workspace_id
            or classification.workflow_id != canonical.workflow_id
        ):
            raise PermissionError("synthetic acceptance is available only to an authenticated synthetic workflow entity")
        if canonical.entity_id != acceptance.entity_id or canonical.approval_status != "approved":
            raise ValueError("synthetic acceptance requires the exact approved proposal workflow")
        artifact = next((a for stage in canonical.stages for a in stage.output_artifacts if a.artifact_id == acceptance.proposal_id), None)
        if (
            artifact is None
            or artifact.checksum != acceptance.proposal_checksum
            or acceptance.proposal_version != _artifact_version(artifact)
        ):
            raise ValueError("synthetic acceptance proposal binding does not match the persisted artefact")
        approval = _matching_approval(canonical, artifact)
        if approval is None or acceptance.actor != str(approval["approver"]):
            raise PermissionError("synthetic acceptance requires the exact authorised proposal approval")
        payload = {
            "classification": "SYNTHETIC / TEST", "classification_event_id": classification.event_id,
            "provider": "none", "stripe_transaction": None,
            "workspace_id": canonical.workspace_id, "client_id": canonical.client_id,
            "entity_id": acceptance.entity_id, "proposal_id": acceptance.proposal_id,
            "proposal_version": acceptance.proposal_version, "proposal_checksum": acceptance.proposal_checksum,
            "actor": acceptance.actor, "source_reference": acceptance.source_reference,
            "approval_recorded_at": str(approval["approved_at"]),
            "approval_binding_digest": str(approval["approval_binding"]["approval_binding_digest"]),
        }
        accepted = self._event(canonical, "synthetic_proposal_accepted", payload)
        paid = self._event(canonical, "synthetic_payment_recorded", {**payload, "payment_status": "simulated_paid", "financial_authorisation": False})
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
        return self.events.append_if_absent(event)


def _artifact_version(artifact) -> str:
    value = str(artifact.metadata.get("version") or "").strip()
    return f"v{value.removeprefix('v')}" if value else "v1"


def _matching_approval(proposal: WorkflowState, artifact) -> dict[str, object] | None:
    """Find the exact human approval already persisted for this immutable artefact."""

    for record in reversed(proposal.approval_history):
        binding = record.get("approval_binding")
        if not isinstance(binding, dict):
            continue
        if (
            str(record.get("approver") or "").strip()
            and str(record.get("approved_at") or "").strip()
            and str(binding.get("approval_binding_digest") or "").strip()
            and binding.get("workflow_id") == proposal.workflow_id
            and binding.get("run_id") == proposal.run_id
            and binding.get("artifact_id") == artifact.artifact_id
            and binding.get("artifact_checksum") == artifact.checksum
            and binding.get("artifact_version") == _artifact_version(artifact)
            and isinstance(binding.get("human_decision"), dict)
            and binding["human_decision"].get("explicit_decision_intent") == "approve"
            and binding["human_decision"].get("verbatim_current_human_instruction_verified") is True
        ):
            return record
    return None
