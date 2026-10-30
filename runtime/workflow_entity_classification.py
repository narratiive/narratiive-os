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
    reason: str
    occurred_at: str
    supersedes_event_id: str = ""

    @classmethod
    def create(
        cls,
        *,
        workspace_id: str,
        entity_id: str,
        workflow_id: str,
        classification: str,
        classifier_id: str,
        authorisation_reference: str,
        reason: str,
        supersedes_event_id: str = "",
    ) -> "WorkflowEntityClassification":
        for name, value in (("workspace_id", workspace_id), ("entity_id", entity_id), ("workflow_id", workflow_id), ("classifier_id", classifier_id), ("authorisation_reference", authorisation_reference), ("reason", reason)):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if classification not in VALID_CLASSIFICATIONS:
            raise ValueError("invalid workflow entity classification")
        return cls(
            event_id=str(uuid4()),
            workspace_id=workspace_id.strip(),
            entity_id=entity_id.strip(),
            workflow_id=workflow_id.strip(),
            classification=classification,
            classifier_id=classifier_id.strip(),
            authorisation_reference=authorisation_reference.strip(),
            reason=reason.strip(),
            occurred_at=datetime.now(timezone.utc).isoformat(),
            supersedes_event_id=supersedes_event_id.strip(),
        )


class FileWorkflowEntityClassificationJournal:
    """Append-only workflow-entity classifications, scoped by workspace."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve() / "entity-classifications"

    def append(
        self,
        event: WorkflowEntityClassification,
        *,
        states: Iterable[WorkflowState],
    ) -> WorkflowEntityClassification:
        matching = [
            state
            for state in states
            if state.workspace_id == event.workspace_id
            and state.entity_id == event.entity_id
            and state.workflow_id == event.workflow_id
        ]
        if not matching:
            raise ValueError("workflow entity and workflow are not registered in the requested workspace")
        prior = self.history(event.workspace_id, event.entity_id)
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

    def history(self, workspace_id: str, entity_id: str) -> tuple[WorkflowEntityClassification, ...]:
        return tuple(
            event for event in self.read_workspace(workspace_id) if event.entity_id == entity_id
        )

    def latest(self, workspace_id: str) -> dict[str, WorkflowEntityClassification]:
        latest: dict[str, WorkflowEntityClassification] = {}
        for event in self.read_workspace(workspace_id):
            prior = latest.get(event.entity_id)
            if prior is None:
                if event.supersedes_event_id:
                    raise ValueError("initial classification event cannot supersede another event")
            elif event.supersedes_event_id != prior.event_id:
                raise ValueError("classification history is not an exact append-only revision chain")
            latest[event.entity_id] = event
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
        return self.journal.append(event, states=tuple(self.states_loader()))
