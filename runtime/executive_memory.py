from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable
from uuid import uuid4


class MemoryKind(StrEnum):
    DECISION = "decision"
    COMMITMENT = "commitment"
    ASSUMPTION = "assumption"
    EVIDENCE = "evidence"
    APPROVAL = "approval"
    REVISION = "revision"
    CONTEXT = "context"
    OUTCOME = "outcome"


@dataclass(frozen=True, slots=True)
class MemoryScope:
    agency_id: str = "narratiive"
    client_id: str | None = None
    run_id: str | None = None
    workstream_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutiveMemoryRecord:
    record_id: str
    created_at: str
    kind: MemoryKind
    summary: str
    detail: str
    scope: MemoryScope
    source: str
    importance: int
    requires_matt: bool
    supersedes: str | None
    previous_hash: str
    record_hash: str

    @classmethod
    def create(
        cls,
        *,
        kind: MemoryKind,
        summary: str,
        detail: str = "",
        scope: MemoryScope | None = None,
        source: str = "runtime",
        importance: int = 3,
        requires_matt: bool = False,
        supersedes: str | None = None,
        previous_hash: str = "GENESIS",
        created_at: str | None = None,
        record_id: str | None = None,
    ) -> "ExecutiveMemoryRecord":
        if not summary.strip():
            raise ValueError("summary must not be empty")
        if importance not in range(1, 6):
            raise ValueError("importance must be between 1 and 5")
        payload = {
            "record_id": record_id or str(uuid4()),
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
            "kind": kind.value,
            "summary": summary.strip(),
            "detail": detail.strip(),
            "scope": asdict(scope or MemoryScope()),
            "source": source,
            "importance": importance,
            "requires_matt": requires_matt,
            "supersedes": supersedes,
            "previous_hash": previous_hash,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            **{**payload, "kind": kind, "scope": scope or MemoryScope(), "record_hash": digest}
        )

    def to_json(self) -> str:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "ExecutiveMemoryRecord":
        payload = json.loads(raw)
        payload["kind"] = MemoryKind(payload["kind"])
        payload["scope"] = MemoryScope(**payload["scope"])
        return cls(**payload)


class ExecutiveMemoryStore:
    """Append-only, hash-chained memory with deterministic scoped retrieval."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _records(self) -> list[ExecutiveMemoryRecord]:
        if not self.path.exists():
            return []
        return [
            ExecutiveMemoryRecord.from_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def append(
        self,
        *,
        kind: MemoryKind,
        summary: str,
        detail: str = "",
        scope: MemoryScope | None = None,
        source: str = "runtime",
        importance: int = 3,
        requires_matt: bool = False,
        supersedes: str | None = None,
    ) -> ExecutiveMemoryRecord:
        records = self._records()
        record = ExecutiveMemoryRecord.create(
            kind=kind,
            summary=summary,
            detail=detail,
            scope=scope,
            source=source,
            importance=importance,
            requires_matt=requires_matt,
            supersedes=supersedes,
            previous_hash=records[-1].record_hash if records else "GENESIS",
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def verify(self) -> bool:
        previous = "GENESIS"
        for record in self._records():
            if record.previous_hash != previous:
                return False
            rebuilt = ExecutiveMemoryRecord.create(
                kind=record.kind,
                summary=record.summary,
                detail=record.detail,
                scope=record.scope,
                source=record.source,
                importance=record.importance,
                requires_matt=record.requires_matt,
                supersedes=record.supersedes,
                previous_hash=record.previous_hash,
                created_at=record.created_at,
                record_id=record.record_id,
            )
            if rebuilt.record_hash != record.record_hash:
                return False
            previous = record.record_hash
        return True

    def select(
        self,
        *,
        scope: MemoryScope,
        kinds: Iterable[MemoryKind] | None = None,
        minimum_importance: int = 1,
        requires_matt: bool | None = None,
        limit: int = 20,
    ) -> tuple[ExecutiveMemoryRecord, ...]:
        allowed = set(kinds) if kinds is not None else None
        selected: list[ExecutiveMemoryRecord] = []
        for record in reversed(self._records()):
            if record.scope.agency_id != scope.agency_id:
                continue
            for field in ("client_id", "run_id", "workstream_id"):
                requested = getattr(scope, field)
                if requested is not None and getattr(record.scope, field) != requested:
                    break
            else:
                if allowed is not None and record.kind not in allowed:
                    continue
                if record.importance < minimum_importance:
                    continue
                if requires_matt is not None and record.requires_matt != requires_matt:
                    continue
                selected.append(record)
                if len(selected) >= limit:
                    break
        return tuple(selected)

    def snapshot(self, target: Path) -> Path:
        target = target.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self.path.read_bytes() if self.path.exists() else b""
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            handle.write(data)
            temporary = Path(handle.name)
        temporary.replace(target)
        return target
