from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


class WorkspaceStateError(RuntimeError):
    """Raised when durable workspace state cannot be read or replayed safely."""


@dataclass(frozen=True, slots=True)
class WorkspaceEvent:
    sequence: int
    event_id: str
    event_type: str
    workspace_id: str
    client_id: str
    occurred_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "occurred_at": self.occurred_at,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkspaceEvent":
        required = ("sequence", "event_id", "event_type", "workspace_id", "client_id", "occurred_at")
        missing = [name for name in required if value.get(name) in (None, "")]
        if missing:
            raise WorkspaceStateError(f"workspace event is missing: {', '.join(missing)}")
        payload = value.get("payload", {})
        if not isinstance(payload, Mapping):
            raise WorkspaceStateError("workspace event payload must be an object")
        return cls(
            sequence=int(value["sequence"]),
            event_id=str(value["event_id"]),
            event_type=str(value["event_type"]),
            workspace_id=str(value["workspace_id"]),
            client_id=str(value["client_id"]),
            occurred_at=str(value["occurred_at"]),
            payload=dict(payload),
        )


@dataclass(slots=True)
class WorkspaceSnapshot:
    workspace_id: str
    active_client_id: str = ""
    active_run_id: str = ""
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    queued_actions: list[dict[str, Any]] = field(default_factory=list)
    completed_actions: list[dict[str, Any]] = field(default_factory=list)
    last_sequence: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "active_client_id": self.active_client_id,
            "active_run_id": self.active_run_id,
            "runs": self.runs,
            "approvals": self.approvals,
            "queued_actions": self.queued_actions,
            "completed_actions": self.completed_actions,
            "last_sequence": self.last_sequence,
            "updated_at": self.updated_at,
        }


class WorkspaceStateRepository:
    """Append-only runtime state with deterministic replay and atomic snapshots.

    The event log is authoritative. New events are replay-validated before they
    are persisted, so an invalid transition can never poison the durable log.
    """

    EVENT_TYPES = {
        "workspace.initialized",
        "client.activated",
        "run.started",
        "run.completed",
        "approval.requested",
        "approval.decided",
        "action.queued",
        "action.completed",
    }

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.events_path = self.state_dir / "workspace-events.jsonl"
        self.snapshot_path = self.state_dir / "workspace-state.json"
        self._lock = threading.RLock()

    def append(
        self,
        event_type: str,
        *,
        workspace_id: str,
        client_id: str = "",
        payload: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
    ) -> WorkspaceSnapshot:
        if event_type not in self.EVENT_TYPES:
            raise WorkspaceStateError(f"unsupported workspace event: {event_type}")
        if not workspace_id.strip():
            raise WorkspaceStateError("workspace_id is required")
        with self._lock:
            events = self.read_events()
            event = WorkspaceEvent(
                sequence=len(events) + 1,
                event_id=event_id or f"evt-{uuid4().hex}",
                event_type=event_type,
                workspace_id=workspace_id,
                client_id=client_id,
                occurred_at=occurred_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                payload=dict(payload or {}),
            )
            prospective = [*events, event]
            snapshot = self.replay(prospective, workspace_id=workspace_id)
            self._append_line(event)
            self._write_snapshot(snapshot)
            return snapshot

    def read_events(self) -> list[WorkspaceEvent]:
        if not self.events_path.exists():
            return []
        events: list[WorkspaceEvent] = []
        try:
            with self.events_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise WorkspaceStateError(f"invalid workspace event JSON at line {line_number}") from exc
                    if not isinstance(raw, Mapping):
                        raise WorkspaceStateError(f"workspace event at line {line_number} must be an object")
                    event = WorkspaceEvent.from_dict(raw)
                    expected = len(events) + 1
                    if event.sequence != expected:
                        raise WorkspaceStateError(
                            f"workspace event sequence gap: expected {expected}, found {event.sequence}"
                        )
                    events.append(event)
        except OSError as exc:
            raise WorkspaceStateError(f"could not read workspace event log: {exc}") from exc
        return events

    def load(self, workspace_id: str) -> WorkspaceSnapshot:
        return self.replay(self.read_events(), workspace_id=workspace_id)

    def rebuild_snapshot(self, workspace_id: str) -> WorkspaceSnapshot:
        with self._lock:
            snapshot = self.load(workspace_id)
            self._write_snapshot(snapshot)
            return snapshot

    def replay(
        self,
        events: Iterable[WorkspaceEvent],
        *,
        workspace_id: str | None = None,
    ) -> WorkspaceSnapshot:
        ordered = list(events)
        resolved_workspace = workspace_id or (ordered[0].workspace_id if ordered else "")
        snapshot = WorkspaceSnapshot(workspace_id=resolved_workspace)
        seen_ids: set[str] = set()
        last_global_sequence = 0
        for event in ordered:
            if event.event_id in seen_ids:
                raise WorkspaceStateError(f"duplicate workspace event id: {event.event_id}")
            if event.sequence <= last_global_sequence:
                raise WorkspaceStateError("workspace events are not in increasing sequence order")
            seen_ids.add(event.event_id)
            last_global_sequence = event.sequence
            if workspace_id and event.workspace_id != workspace_id:
                continue
            if snapshot.workspace_id and event.workspace_id != snapshot.workspace_id:
                raise WorkspaceStateError("cannot replay multiple workspaces into one snapshot")
            snapshot.workspace_id = event.workspace_id
            self._apply(snapshot, event)
            snapshot.last_sequence = event.sequence
            snapshot.updated_at = event.occurred_at
        return snapshot

    @staticmethod
    def _apply(snapshot: WorkspaceSnapshot, event: WorkspaceEvent) -> None:
        payload = dict(event.payload)
        if event.event_type == "workspace.initialized":
            return
        if event.event_type == "client.activated":
            snapshot.active_client_id = event.client_id
            return
        if event.event_type == "run.started":
            run_id = str(payload.get("run_id", "")).strip()
            if not run_id:
                raise WorkspaceStateError("run.started requires payload.run_id")
            snapshot.active_client_id = event.client_id or snapshot.active_client_id
            snapshot.active_run_id = run_id
            snapshot.runs[run_id] = {**payload, "run_id": run_id, "client_id": event.client_id, "status": "active"}
            return
        if event.event_type == "run.completed":
            run_id = str(payload.get("run_id", "")).strip()
            if not run_id or run_id not in snapshot.runs:
                raise WorkspaceStateError("run.completed references an unknown run")
            snapshot.runs[run_id] = {**snapshot.runs[run_id], **payload, "status": "completed"}
            if snapshot.active_run_id == run_id:
                snapshot.active_run_id = ""
            return
        if event.event_type == "approval.requested":
            approval_id = str(payload.get("approval_id", "")).strip()
            if not approval_id:
                raise WorkspaceStateError("approval.requested requires payload.approval_id")
            snapshot.approvals[approval_id] = {
                **payload,
                "approval_id": approval_id,
                "client_id": event.client_id,
                "status": "pending",
            }
            return
        if event.event_type == "approval.decided":
            approval_id = str(payload.get("approval_id", "")).strip()
            if not approval_id or approval_id not in snapshot.approvals:
                raise WorkspaceStateError("approval.decided references an unknown approval")
            decision = str(payload.get("decision", "")).strip()
            if not decision:
                raise WorkspaceStateError("approval.decided requires payload.decision")
            snapshot.approvals[approval_id] = {**snapshot.approvals[approval_id], **payload, "status": decision}
            return
        if event.event_type == "action.queued":
            action_id = str(payload.get("action_id", "")).strip()
            if not action_id:
                raise WorkspaceStateError("action.queued requires payload.action_id")
            if any(item.get("action_id") == action_id for item in snapshot.queued_actions):
                raise WorkspaceStateError(f"action is already queued: {action_id}")
            snapshot.queued_actions.append({**payload, "action_id": action_id, "client_id": event.client_id})
            return
        if event.event_type == "action.completed":
            action_id = str(payload.get("action_id", "")).strip()
            matches = [item for item in snapshot.queued_actions if item.get("action_id") == action_id]
            if not action_id or not matches:
                raise WorkspaceStateError("action.completed references an unknown queued action")
            snapshot.queued_actions = [item for item in snapshot.queued_actions if item.get("action_id") != action_id]
            snapshot.completed_actions.append({**matches[0], **payload, "status": "completed"})
            return
        raise WorkspaceStateError(f"unsupported workspace event: {event.event_type}")

    def _append_line(self, event: WorkspaceEvent) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True) + "\n"
        try:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise WorkspaceStateError(f"could not append workspace event: {exc}") from exc

    def _write_snapshot(self, snapshot: WorkspaceSnapshot) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        value = snapshot.to_dict()
        canonical = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        envelope = {"state": value, "sha256": hashlib.sha256(canonical).hexdigest()}
        temporary = self.snapshot_path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, self.snapshot_path)
        except OSError as exc:
            raise WorkspaceStateError(f"could not write workspace snapshot: {exc}") from exc
