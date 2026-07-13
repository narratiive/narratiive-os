from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from .models import WorkflowState
from .serialization import workflow_from_dict, workflow_to_dict


class RunNotFound(KeyError):
    """Raised when a requested workflow run does not exist."""


class WorkflowRunRepository(Protocol):
    def save(self, state: WorkflowState) -> None: ...

    def load(self, run_id: str) -> WorkflowState: ...

    def exists(self, run_id: str) -> bool: ...

    def list_run_ids(self) -> list[str]: ...


class EventLog(Protocol):
    def append(self, event: "WorkflowEvent") -> None: ...

    def read(self, run_id: str) -> list["WorkflowEvent"]: ...


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    event_id: str
    run_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: str

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> "WorkflowEvent":
        if not event_id.strip():
            raise ValueError("event_id must not be empty")
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        if not event_type.strip():
            raise ValueError("event_type must not be empty")
        return cls(
            event_id=event_id,
            run_id=run_id,
            event_type=event_type,
            payload=dict(payload or {}),
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowEvent":
        return cls(
            event_id=data["event_id"],
            run_id=data["run_id"],
            event_type=data["event_type"],
            payload=dict(data.get("payload") or {}),
            occurred_at=data["occurred_at"],
        )


class FileWorkflowRunRepository:
    """Atomic JSON persistence for workflow snapshots."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, state: WorkflowState) -> None:
        target = self._path(state.run_id)
        payload = json.dumps(workflow_to_dict(state), indent=2, sort_keys=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{state.run_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, run_id: str) -> WorkflowState:
        path = self._path(run_id)
        if not path.exists():
            raise RunNotFound(run_id)
        with path.open("r", encoding="utf-8") as handle:
            return workflow_from_dict(json.load(handle))

    def exists(self, run_id: str) -> bool:
        return self._path(run_id).exists()

    def list_run_ids(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json") if path.is_file())

    def _path(self, run_id: str) -> Path:
        _validate_identifier(run_id, "run_id")
        return self.root / f"{run_id}.json"


class JsonlEventLog:
    """Append-only JSONL event history, partitioned by workflow run."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, event: WorkflowEvent) -> None:
        path = self._path(event.run_id)
        line = json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read(self, run_id: str) -> list[WorkflowEvent]:
        path = self._path(run_id)
        if not path.exists():
            return []
        events: list[WorkflowEvent] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    events.append(WorkflowEvent.from_dict(json.loads(line)))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid event at {path}:{line_number}") from exc
        return events

    def contains(self, run_id: str, event_id: str) -> bool:
        return any(event.event_id == event_id for event in self.read(run_id))

    def append_many(self, events: Iterable[WorkflowEvent]) -> None:
        for event in events:
            self.append(event)

    def _path(self, run_id: str) -> Path:
        _validate_identifier(run_id, "run_id")
        return self.root / f"{run_id}.jsonl"


def _validate_identifier(value: str, field_name: str) -> None:
    if not value or value in {".", ".."}:
        raise ValueError(f"{field_name} must not be empty")
    if Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} must be a safe filename identifier")
