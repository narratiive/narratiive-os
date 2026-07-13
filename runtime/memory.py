from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol


class MemoryKind(str, Enum):
    DECISION = "decision"
    ASSUMPTION = "assumption"
    EVIDENCE = "evidence"
    REVISION = "revision"
    APPROVAL = "approval"
    CONTEXT = "context"


class MemoryScope(str, Enum):
    CLIENT = "client"
    RUN = "run"


class MemoryIntegrityError(ValueError):
    """Raised when a persisted memory journal fails its checksum chain."""


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    client_id: str
    kind: MemoryKind
    scope: MemoryScope
    content: str
    run_id: str | None = None
    origin_stage_id: str | None = None
    stage_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sequence: int = 0
    previous_checksum: str = ""
    checksum: str = ""

    def __post_init__(self) -> None:
        _safe(self.memory_id, "memory_id")
        _safe(self.client_id, "client_id")
        if self.scope == MemoryScope.RUN:
            _safe(self.run_id or "", "run_id")
        elif self.run_id is not None:
            raise ValueError("client-scoped memory must not define run_id")
        if not self.content.strip():
            raise ValueError("content must not be empty")
        for stage_id in self.stage_ids:
            _safe(stage_id, "stage_id")
        if self.origin_stage_id is not None:
            _safe(self.origin_stage_id, "origin_stage_id")
        if self.sequence < 0:
            raise ValueError("sequence must not be negative")
        if not self.created_at.strip():
            raise ValueError("created_at must not be empty")
        object.__setattr__(self, "stage_ids", tuple(self.stage_ids))
        object.__setattr__(
            self,
            "source_artifact_ids",
            tuple(self.source_artifact_ids),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self, *, include_checksum: bool = True) -> dict[str, Any]:
        payload = {
            "memory_id": self.memory_id,
            "client_id": self.client_id,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "scope": self.scope.value,
            "content": self.content,
            "origin_stage_id": self.origin_stage_id,
            "stage_ids": list(self.stage_ids),
            "source_artifact_ids": list(self.source_artifact_ids),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "sequence": self.sequence,
            "previous_checksum": self.previous_checksum,
        }
        if include_checksum:
            payload["checksum"] = self.checksum
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryRecord":
        return cls(
            memory_id=str(data["memory_id"]),
            client_id=str(data["client_id"]),
            run_id=str(data["run_id"]) if data.get("run_id") is not None else None,
            kind=MemoryKind(str(data["kind"])),
            scope=MemoryScope(str(data["scope"])),
            content=str(data["content"]),
            origin_stage_id=(
                str(data["origin_stage_id"])
                if data.get("origin_stage_id") is not None
                else None
            ),
            stage_ids=tuple(str(item) for item in data.get("stage_ids") or ()),
            source_artifact_ids=tuple(
                str(item) for item in data.get("source_artifact_ids") or ()
            ),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data["created_at"]),
            sequence=int(data.get("sequence", 0)),
            previous_checksum=str(data.get("previous_checksum", "")),
            checksum=str(data.get("checksum", "")),
        )


class MemoryStore(Protocol):
    def append(self, record: MemoryRecord) -> MemoryRecord: ...

    def read(self, client_id: str, run_id: str | None = None) -> tuple[MemoryRecord, ...]: ...


class FileMemoryStore:
    """Append-only, checksum-chained memory journals partitioned by client."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, record: MemoryRecord) -> MemoryRecord:
        if record.sequence or record.previous_checksum or record.checksum:
            raise ValueError("only new memory records may be appended")
        existing = self._read_all(record.client_id)
        if any(item.memory_id == record.memory_id for item in existing):
            raise ValueError(f"memory_id already exists: {record.memory_id}")
        stored = replace(
            record,
            sequence=len(existing) + 1,
            previous_checksum=existing[-1].checksum if existing else "",
        )
        stored = replace(stored, checksum=_record_checksum(stored))
        line = json.dumps(
            stored.to_dict(),
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._path(record.client_id).open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return stored

    def contains(self, client_id: str, memory_id: str) -> bool:
        return any(
            record.memory_id == memory_id for record in self._read_all(client_id)
        )

    def read(
        self,
        client_id: str,
        run_id: str | None = None,
    ) -> tuple[MemoryRecord, ...]:
        _safe(client_id, "client_id")
        if run_id is not None:
            _safe(run_id, "run_id")
        return tuple(
            record
            for record in self._read_all(client_id)
            if record.scope == MemoryScope.CLIENT or record.run_id == run_id
        )

    def _read_all(self, client_id: str) -> tuple[MemoryRecord, ...]:
        path = self._path(client_id)
        if not path.exists():
            return ()
        records: list[MemoryRecord] = []
        previous_checksum = ""
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = MemoryRecord.from_dict(json.loads(line))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise MemoryIntegrityError(
                        f"invalid memory at {path}:{line_number}"
                    ) from exc
                if record.client_id != client_id:
                    raise MemoryIntegrityError(
                        f"client scope mismatch at {path}:{line_number}"
                    )
                if record.sequence != line_number:
                    raise MemoryIntegrityError(
                        f"memory sequence mismatch at {path}:{line_number}"
                    )
                if record.previous_checksum != previous_checksum:
                    raise MemoryIntegrityError(
                        f"memory chain mismatch at {path}:{line_number}"
                    )
                if record.checksum != _record_checksum(record):
                    raise MemoryIntegrityError(
                        f"memory checksum mismatch at {path}:{line_number}"
                    )
                records.append(record)
                previous_checksum = record.checksum
        return tuple(records)

    def _path(self, client_id: str) -> Path:
        return self.root / f"{_safe(client_id, 'client_id')}.jsonl"


DEFAULT_SPECIALIST_MEMORY_POLICY: dict[str, frozenset[MemoryKind]] = {
    "research_analyst": frozenset(
        {
            MemoryKind.CONTEXT,
            MemoryKind.EVIDENCE,
            MemoryKind.ASSUMPTION,
            MemoryKind.DECISION,
            MemoryKind.REVISION,
        }
    ),
    "strategy_director": frozenset(
        {
            MemoryKind.CONTEXT,
            MemoryKind.EVIDENCE,
            MemoryKind.ASSUMPTION,
            MemoryKind.DECISION,
            MemoryKind.REVISION,
            MemoryKind.APPROVAL,
        }
    ),
    "campaign_world_generator": frozenset(
        {
            MemoryKind.CONTEXT,
            MemoryKind.ASSUMPTION,
            MemoryKind.DECISION,
            MemoryKind.REVISION,
            MemoryKind.APPROVAL,
        }
    ),
    "creative_director": frozenset(
        {
            MemoryKind.CONTEXT,
            MemoryKind.DECISION,
            MemoryKind.REVISION,
            MemoryKind.APPROVAL,
        }
    ),
    "quality_reviewer": frozenset(MemoryKind),
}


class SpecialistMemorySelector:
    """Selects run-safe memory in journal order using specialist policies."""

    def __init__(
        self,
        store: MemoryStore,
        policy: Mapping[str, Iterable[MemoryKind]] | None = None,
    ) -> None:
        self.store = store
        selected_policy = policy or DEFAULT_SPECIALIST_MEMORY_POLICY
        self.policy = {
            stage_id: frozenset(kinds)
            for stage_id, kinds in selected_policy.items()
        }

    def select(
        self,
        *,
        client_id: str,
        run_id: str,
        stage_id: str,
    ) -> tuple[MemoryRecord, ...]:
        try:
            allowed_kinds = self.policy[stage_id]
        except KeyError as exc:
            raise ValueError(f"no memory policy for specialist: {stage_id}") from exc
        return tuple(
            record
            for record in self.store.read(client_id, run_id)
            if record.kind in allowed_kinds
            and (not record.stage_ids or stage_id in record.stage_ids)
        )


def _record_checksum(record: MemoryRecord) -> str:
    payload = json.dumps(
        record.to_dict(include_checksum=False),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe(value: str, field_name: str) -> str:
    safe = value.strip()
    if (
        not safe
        or safe in {".", ".."}
        or Path(safe).name != safe
        or "/" in safe
        or "\\" in safe
    ):
        raise ValueError(f"{field_name} must be a safe identifier")
    return safe
