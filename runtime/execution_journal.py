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


class ExecutionJournalError(RuntimeError):
    """Raised when Tony's decision journal cannot be trusted."""


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    sequence: int
    record_id: str
    decision_id: str
    workspace_id: str
    client_id: str
    action: str
    rationale: str
    actor: str
    status: str
    occurred_at: str
    repository_revision: str = ""
    state_hash: str = ""
    artifacts: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    record_hash: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "record_id": self.record_id,
            "decision_id": self.decision_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "action": self.action,
            "rationale": self.rationale,
            "actor": self.actor,
            "status": self.status,
            "occurred_at": self.occurred_at,
            "repository_revision": self.repository_revision,
            "state_hash": self.state_hash,
            "artifacts": list(self.artifacts),
            "metadata": dict(self.metadata),
            "previous_hash": self.previous_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "record_hash": self.record_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionRecord":
        required = (
            "sequence", "record_id", "decision_id", "workspace_id", "action",
            "rationale", "actor", "status", "occurred_at", "record_hash",
        )
        missing = [name for name in required if value.get(name) in (None, "")]
        if missing:
            raise ExecutionJournalError(f"execution record is missing: {', '.join(missing)}")
        metadata = value.get("metadata", {})
        artifacts = value.get("artifacts", [])
        if not isinstance(metadata, Mapping):
            raise ExecutionJournalError("execution record metadata must be an object")
        if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
            raise ExecutionJournalError("execution record artifacts must be a string list")
        return cls(
            sequence=int(value["sequence"]),
            record_id=str(value["record_id"]),
            decision_id=str(value["decision_id"]),
            workspace_id=str(value["workspace_id"]),
            client_id=str(value.get("client_id", "")),
            action=str(value["action"]),
            rationale=str(value["rationale"]),
            actor=str(value["actor"]),
            status=str(value["status"]),
            occurred_at=str(value["occurred_at"]),
            repository_revision=str(value.get("repository_revision", "")),
            state_hash=str(value.get("state_hash", "")),
            artifacts=tuple(artifacts),
            metadata=dict(metadata),
            previous_hash=str(value.get("previous_hash", "")),
            record_hash=str(value["record_hash"]),
        )


class ExecutionJournal:
    """Append-only, hash-chained provenance for autonomous Tony decisions."""

    STATUSES = {"selected", "dispatched", "completed", "failed", "blocked", "rolled_back"}

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "execution-journal.jsonl"
        self._lock = threading.RLock()

    def append(
        self,
        *,
        decision_id: str,
        workspace_id: str,
        action: str,
        rationale: str,
        actor: str,
        status: str,
        client_id: str = "",
        repository_revision: str = "",
        state_hash: str = "",
        artifacts: Iterable[str] = (),
        metadata: Mapping[str, Any] | None = None,
        record_id: str | None = None,
        occurred_at: str | None = None,
    ) -> ExecutionRecord:
        required = {
            "decision_id": decision_id,
            "workspace_id": workspace_id,
            "action": action,
            "rationale": rationale,
            "actor": actor,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ExecutionJournalError(f"execution record is missing: {', '.join(missing)}")
        if status not in self.STATUSES:
            raise ExecutionJournalError(f"unsupported execution status: {status}")
        artifact_values = tuple(str(item) for item in artifacts)
        if any(not item.strip() for item in artifact_values):
            raise ExecutionJournalError("artifacts must not contain empty values")

        with self._lock:
            records = self.read_all()
            if any(record.record_id == record_id for record in records if record_id):
                raise ExecutionJournalError(f"duplicate execution record id: {record_id}")
            previous_hash = records[-1].record_hash if records else ""
            record = ExecutionRecord(
                sequence=len(records) + 1,
                record_id=record_id or f"exec-{uuid4().hex}",
                decision_id=decision_id,
                workspace_id=workspace_id,
                client_id=client_id,
                action=action,
                rationale=rationale,
                actor=actor,
                status=status,
                occurred_at=occurred_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                repository_revision=repository_revision,
                state_hash=state_hash,
                artifacts=artifact_values,
                metadata=dict(metadata or {}),
                previous_hash=previous_hash,
            )
            record = ExecutionRecord(**{**record.__dict__, "record_hash": self._hash(record)})
            self._append_line(record)
            return record

    def read_all(self) -> list[ExecutionRecord]:
        if not self.path.exists():
            return []
        records: list[ExecutionRecord] = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ExecutionJournalError(f"invalid execution journal JSON at line {line_number}") from exc
                    if not isinstance(raw, Mapping):
                        raise ExecutionJournalError(f"execution record at line {line_number} must be an object")
                    record = ExecutionRecord.from_dict(raw)
                    expected_sequence = len(records) + 1
                    if record.sequence != expected_sequence:
                        raise ExecutionJournalError(
                            f"execution journal sequence gap: expected {expected_sequence}, found {record.sequence}"
                        )
                    expected_previous = records[-1].record_hash if records else ""
                    if record.previous_hash != expected_previous:
                        raise ExecutionJournalError(f"execution journal chain break at sequence {record.sequence}")
                    if record.record_hash != self._hash(record):
                        raise ExecutionJournalError(f"execution record hash mismatch at sequence {record.sequence}")
                    records.append(record)
        except OSError as exc:
            raise ExecutionJournalError(f"could not read execution journal: {exc}") from exc
        return records

    def history(self, decision_id: str) -> list[ExecutionRecord]:
        return [record for record in self.read_all() if record.decision_id == decision_id]

    def latest(self, decision_id: str) -> ExecutionRecord | None:
        records = self.history(decision_id)
        return records[-1] if records else None

    def verify(self) -> dict[str, Any]:
        records = self.read_all()
        return {
            "ok": True,
            "records": len(records),
            "decisions": len({record.decision_id for record in records}),
            "head_hash": records[-1].record_hash if records else "",
        }

    @staticmethod
    def _hash(record: ExecutionRecord) -> str:
        canonical = json.dumps(record.unsigned_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _append_line(self, record: ExecutionRecord) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise ExecutionJournalError(f"could not append execution record: {exc}") from exc
