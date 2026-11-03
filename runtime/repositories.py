from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
import fcntl
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
    workspace_id: str = "legacy"

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        workspace_id: str = "legacy",
    ) -> "WorkflowEvent":
        if not event_id.strip():
            raise ValueError("event_id must not be empty")
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        if not event_type.strip():
            raise ValueError("event_type must not be empty")
        _validate_identifier(workspace_id, "workspace_id")
        return cls(
            event_id=event_id,
            run_id=run_id,
            event_type=event_type,
            payload=dict(payload or {}),
            occurred_at=datetime.now(timezone.utc).isoformat(),
            workspace_id=workspace_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
            "workspace_id": self.workspace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowEvent":
        return cls(
            event_id=data["event_id"],
            run_id=data["run_id"],
            event_type=data["event_type"],
            payload=dict(data.get("payload") or {}),
            occurred_at=data["occurred_at"],
            workspace_id=str(data.get("workspace_id", "legacy")),
        )


class FileWorkflowRunRepository:
    """Atomic JSON persistence for workflow snapshots."""

    def __init__(
        self,
        root: str | Path,
        *,
        workspace_id: str = "legacy",
        client_id: str = "legacy",
    ) -> None:
        self.root = Path(root)
        _validate_identifier(workspace_id, "workspace_id")
        _validate_identifier(client_id, "client_id")
        self.workspace_id = workspace_id
        self.client_id = client_id
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, state: WorkflowState) -> None:
        if state.workspace_id != self.workspace_id or state.client_id != self.client_id:
            raise ValueError("workflow belongs to a different workspace")
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
            state = workflow_from_dict(json.load(handle))
        if state.workspace_id != self.workspace_id or state.client_id != self.client_id:
            raise ValueError("workflow belongs to a different workspace")
        return state

    def exists(self, run_id: str) -> bool:
        return self._path(run_id).exists()

    def list_run_ids(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json") if path.is_file())

    def _path(self, run_id: str) -> Path:
        _validate_identifier(run_id, "run_id")
        return self.root / f"{run_id}.json"


class JsonlEventLog:
    """Append-only JSONL event history, partitioned by workflow run."""

    _locks_guard = threading.Lock()
    _run_locks: dict[str, threading.RLock] = {}
    _transaction_ownership = threading.local()

    def __init__(self, root: str | Path, *, workspace_id: str = "legacy") -> None:
        self.root = Path(root)
        _validate_identifier(workspace_id, "workspace_id")
        self.workspace_id = workspace_id
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, event: WorkflowEvent) -> None:
        if event.workspace_id != self.workspace_id:
            raise ValueError("event belongs to a different workspace")
        path = self._path(event.run_id)
        line = json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True)
        with self._run_lock(event.run_id):
            with self._process_lock_unless_owned(event.run_id):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())

    def read(self, run_id: str) -> list[WorkflowEvent]:
        path = self._path(run_id)
        with self._run_lock(run_id):
            with self._process_lock_unless_owned(run_id):
                if not path.exists():
                    return []
                events: list[WorkflowEvent] = []
                with path.open("r", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if not line.strip():
                            continue
                        try:
                            event = WorkflowEvent.from_dict(json.loads(line))
                            if event.workspace_id != self.workspace_id:
                                raise ValueError("event belongs to a different workspace")
                            events.append(event)
                        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                            raise ValueError(f"invalid event at {path}:{line_number}") from exc
                return events

    def contains(self, run_id: str, event_id: str) -> bool:
        return any(event.event_id == event_id for event in self.read(run_id))

    def append_many(self, events: Iterable[WorkflowEvent]) -> None:
        for event in events:
            self.append(event)

    @contextmanager
    def transaction(self, run_id: str):
        """Own one run's event stream and roll back only this failed transaction."""
        with self._run_lock(run_id):
            with self._process_lock_unless_owned(run_id):
                key = self._lock_key(run_id)
                owned = self._owned_transactions()
                owned[key] = owned.get(key, 0) + 1
                path = self._path(run_id)
                checkpoint = path.stat().st_size if path.exists() else 0
                try:
                    yield
                except Exception:
                    if path.exists():
                        with path.open("r+b") as handle:
                            handle.truncate(checkpoint)
                            handle.flush()
                            os.fsync(handle.fileno())
                    raise
                finally:
                    if owned[key] == 1:
                        del owned[key]
                    else:
                        owned[key] -= 1

    def _run_lock(self, run_id: str) -> threading.RLock:
        key = self._lock_key(run_id)
        with self._locks_guard:
            return self._run_locks.setdefault(key, threading.RLock())

    def _lock_key(self, run_id: str) -> str:
        return str(self._path(run_id).resolve())

    def _owned_transactions(self) -> dict[str, int]:
        owned = getattr(self._transaction_ownership, "runs", None)
        if owned is None:
            owned = {}
            self._transaction_ownership.runs = owned
        return owned

    @contextmanager
    def _process_lock_unless_owned(self, run_id: str):
        key = self._lock_key(run_id)
        if self._owned_transactions().get(key, 0):
            yield
            return
        lock_path = self.root / f".{run_id}.lock"
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _path(self, run_id: str) -> Path:
        _validate_identifier(run_id, "run_id")
        return self.root / f"{run_id}.jsonl"


def _validate_identifier(value: str, field_name: str) -> None:
    if not value or value in {".", ".."}:
        raise ValueError(f"{field_name} must not be empty")
    if Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} must be a safe filename identifier")
