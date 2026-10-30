from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

from runtime.models import WorkflowState


GENUINE_CLIENT = "genuine_client"
INTERNAL_SYNTHETIC_TEST = "internal_synthetic_test"
VALID_CLASSIFICATIONS = frozenset({GENUINE_CLIENT, INTERNAL_SYNTHETIC_TEST})


@dataclass(frozen=True, slots=True)
class WorkflowEntityClassification:
    """One append-only, authorised classification of a workflow entity."""

    event_id: str
    workspace_id: str
    entity_id: str
    workflow_id: str
    classification: str
    classifier_id: str
    authorisation_reference: str
    authorisation_turn_id: str
    authorisation_proof: str
    reason: str
    occurred_at: str
    supersedes_event_id: str = ""
    client_id: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("workspace_id", self.workspace_id),
            ("entity_id", self.entity_id),
            ("workflow_id", self.workflow_id),
            ("classifier_id", self.classifier_id),
            ("authorisation_reference", self.authorisation_reference),
            ("authorisation_turn_id", self.authorisation_turn_id),
            ("authorisation_proof", self.authorisation_proof),
            ("reason", self.reason),
            ("occurred_at", self.occurred_at),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.classification not in VALID_CLASSIFICATIONS:
            raise ValueError("invalid workflow entity classification")
        try:
            datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("occurred_at must be an ISO-8601 timestamp") from exc

    @classmethod
    def create(
        cls,
        *,
        workspace_id: str,
        client_id: str,
        entity_id: str,
        workflow_id: str,
        classification: str,
        classifier_id: str,
        authorisation_reference: str,
        authorisation_turn_id: str,
        authorisation_proof: str,
        reason: str,
        supersedes_event_id: str = "",
    ) -> "WorkflowEntityClassification":
        return cls(
            event_id=str(uuid4()),
            workspace_id=workspace_id.strip(),
            client_id=client_id.strip(),
            entity_id=entity_id.strip(),
            workflow_id=workflow_id.strip(),
            classification=classification,
            classifier_id=classifier_id.strip(),
            authorisation_reference=authorisation_reference.strip(),
            authorisation_turn_id=authorisation_turn_id.strip(),
            authorisation_proof=authorisation_proof.strip(),
            reason=reason.strip(),
            occurred_at=datetime.now(timezone.utc).isoformat(),
            supersedes_event_id=supersedes_event_id.strip(),
        )


class FileWorkflowEntityClassificationJournal:
    """Append-only workflow-entity classifications, scoped by workspace."""

    def __init__(self, root: str | Path, *, authorised_classifier_id: str = "") -> None:
        self.root = Path(root).resolve() / "entity-classifications"
        self.authorised_classifier_id = authorised_classifier_id.strip()

    def append(
        self,
        event: WorkflowEntityClassification,
        *,
        states: Iterable[WorkflowState],
        principal_id: str = "",
    ) -> WorkflowEntityClassification:
        if not self.authorised_classifier_id:
            raise PermissionError("classification journal is read-only without an authorised classifier")
        if principal_id.strip() != self.authorised_classifier_id or event.classifier_id != self.authorised_classifier_id:
            raise PermissionError("workflow entity classification requires the authorised classifier")
        matching = [
            state
            for state in states
            if state.workspace_id == event.workspace_id
            and state.client_id == event.client_id
            and state.entity_id == event.entity_id
            and state.workflow_id == event.workflow_id
        ]
        if not event.client_id:
            raise ValueError("workflow entity classification requires an exact client scope")
        if not matching:
            raise ValueError("workflow entity and workflow are not registered in the requested workspace")
        prior = self.history(
            event.workspace_id, event.entity_id,
            workflow_id=event.workflow_id, client_id=event.client_id,
        )
        if prior:
            if not event.supersedes_event_id:
                raise ValueError("classification revision must supersede the latest event")
            if event.supersedes_event_id != prior[-1].event_id:
                raise ValueError("classification supersession does not match the latest event")
        elif event.supersedes_event_id:
            raise ValueError("initial classification cannot supersede an event")
        path = self._path(event.workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(path, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True, separators=(",", ":")))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def history(
        self,
        workspace_id: str,
        entity_id: str,
        *,
        workflow_id: str = "",
        client_id: str = "",
    ) -> tuple[WorkflowEntityClassification, ...]:
        return tuple(
            event
            for event in self.read_workspace(workspace_id)
            if event.entity_id == entity_id
            and (not workflow_id or event.workflow_id == workflow_id)
            and (not client_id or event.client_id == client_id)
        )

    def classification_for(
        self,
        state: WorkflowState,
        *,
        states: Iterable[WorkflowState],
    ) -> WorkflowEntityClassification | None:
        """Resolve a classification only within the exact client/workflow scope.

        Legacy append-only records without ``client_id`` remain readable, but are
        honoured only when all matching persisted states resolve to one client.
        New classification records always carry ``client_id``.
        """

        if not self.authorised_classifier_id:
            return None
        candidates = [
            event for event in self.read_workspace(state.workspace_id)
            if event.entity_id == state.entity_id and event.workflow_id == state.workflow_id
        ]
        scoped = [event for event in candidates if event.client_id == state.client_id]
        if scoped:
            return scoped[-1]
        legacy = [event for event in candidates if not event.client_id]
        matching_clients = {
            item.client_id for item in states
            if item.workspace_id == state.workspace_id
            and item.entity_id == state.entity_id
            and item.workflow_id == state.workflow_id
        }
        if len(matching_clients) == 1 and state.client_id in matching_clients:
            return legacy[-1] if legacy else None
        return None

    def latest(self, workspace_id: str) -> dict[str, WorkflowEntityClassification]:
        # A missing founder identity must never turn an old local record into a
        # synthetic classification.  Showing the work is the safe failure mode.
        if not self.authorised_classifier_id:
            return {}
        latest: dict[str, WorkflowEntityClassification] = {}
        for event in self.read_workspace(workspace_id):
            if not event.client_id:
                # Client-less legacy evidence is deliberately unavailable to
                # broad entity lookups. Call classification_for with the
                # authoritative state to resolve it safely.
                continue
            key = f"{event.client_id}\0{event.entity_id}\0{event.workflow_id}"
            prior = latest.get(key)
            if prior is None:
                if event.supersedes_event_id:
                    raise ValueError("initial classification event cannot supersede another event")
            elif event.supersedes_event_id != prior.event_id:
                raise ValueError("classification history is not an exact append-only revision chain")
            latest[key] = event
        return latest

    def read_workspace(self, workspace_id: str) -> tuple[WorkflowEntityClassification, ...]:
        path = self._path(workspace_id)
        if not path.exists():
            return ()
        events: list[WorkflowEntityClassification] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                event = WorkflowEntityClassification(**raw)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid workflow classification event at {path}:{line_number}") from exc
            if event.workspace_id != workspace_id or event.classification not in VALID_CLASSIFICATIONS:
                raise ValueError(f"invalid workflow classification scope at {path}:{line_number}")
            if self.authorised_classifier_id and event.classifier_id != self.authorised_classifier_id:
                raise ValueError(f"unauthorised workflow classifier at {path}:{line_number}")
            events.append(event)
        return tuple(events)

    def _path(self, workspace_id: str) -> Path:
        safe = workspace_id.strip()
        if not safe or Path(safe).name != safe:
            raise ValueError("workspace_id must be a safe identifier")
        return self.root / f"{safe}.jsonl"


class WorkflowEntityClassificationService:
    """The narrow write boundary for authorised entity classifications."""

    def __init__(
        self,
        journal: FileWorkflowEntityClassificationJournal,
        states_loader: Callable[[], Iterable[WorkflowState]],
        *,
        workspace_id: str,
        authorised_classifier_id: str,
    ) -> None:
        self.journal = journal
        self.states_loader = states_loader
        self.workspace_id = workspace_id.strip()
        self.authorised_classifier_id = authorised_classifier_id.strip()
        if not self.workspace_id or not self.authorised_classifier_id:
            raise ValueError("classification service requires an exact workspace and authorised classifier")

    def record(self, event: WorkflowEntityClassification, *, principal_id: str) -> WorkflowEntityClassification:
        if principal_id.strip() != self.authorised_classifier_id:
            raise PermissionError("workflow entity classification requires the authorised classifier")
        if event.workspace_id != self.workspace_id or event.classifier_id != principal_id.strip():
            raise PermissionError("workflow entity classification scope or classifier mismatch")
        return self.journal.append(
            event,
            states=tuple(self.states_loader()),
            principal_id=principal_id,
        )
