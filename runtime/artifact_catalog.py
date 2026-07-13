from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import ArtifactRef


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact: ArtifactRef
    run_id: str
    stage_id: str
    version: int
    parent_artifact_ids: tuple[str, ...] = ()
    producer: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    workspace_id: str = "legacy"

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.stage_id.strip():
            raise ValueError("run_id and stage_id must not be empty")
        _safe(self.workspace_id, "workspace_id")
        if self.version <= 0:
            raise ValueError("version must be positive")
        if self.artifact.artifact_id in self.parent_artifact_ids:
            raise ValueError("artifact cannot be its own parent")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact"] = asdict(self.artifact)
        payload["parent_artifact_ids"] = list(self.parent_artifact_ids)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRecord":
        return cls(
            artifact=ArtifactRef(**data["artifact"]),
            run_id=data["run_id"],
            stage_id=data["stage_id"],
            version=int(data["version"]),
            parent_artifact_ids=tuple(data.get("parent_artifact_ids") or ()),
            producer=data.get("producer"),
            created_at=data["created_at"],
            workspace_id=str(data.get("workspace_id", "legacy")),
        )


class FileArtifactCatalog:
    """Immutable content store and lineage index for workflow artifacts."""

    def __init__(self, root: str | Path, *, workspace_id: str = "legacy") -> None:
        self.root = Path(root)
        self.workspace_id = _safe(workspace_id, "workspace_id")
        self.content_root = self.root / "content"
        self.records_root = self.root / "records"
        self.content_root.mkdir(parents=True, exist_ok=True)
        self.records_root.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        *,
        run_id: str,
        stage_id: str,
        artifact_type: str,
        content: str,
        parent_artifact_ids: Iterable[str] = (),
        producer: str | None = None,
        extension: str = ".md",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        run_id = _safe(run_id, "run_id")
        stage_id = _safe(stage_id, "stage_id")
        artifact_type = artifact_type.strip()
        if not artifact_type:
            raise ValueError("artifact_type must not be empty")
        if not content:
            raise ValueError("content must not be empty")
        if not extension.startswith(".") or "/" in extension or "\\" in extension:
            raise ValueError("invalid extension")
        parent_ids = tuple(dict.fromkeys(parent_artifact_ids))
        for parent_id in parent_ids:
            if not self.get(parent_id):
                raise ValueError(
                    f"parent artifact not found in workspace {self.workspace_id}: "
                    f"{parent_id}"
                )

        data = content.encode("utf-8")
        checksum = hashlib.sha256(data).hexdigest()
        artifact_id = f"art-{checksum}"
        content_path = self.content_root / f"{checksum}{extension}"
        if not content_path.exists():
            self._atomic_write_bytes(content_path, data)

        version = self._next_version(run_id, stage_id, artifact_type)
        artifact = ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            location=str(content_path),
            checksum=checksum,
            metadata={
                **dict(metadata or {}),
                "workspace_id": self.workspace_id,
            },
        )
        record = ArtifactRecord(
            artifact=artifact,
            run_id=run_id,
            stage_id=stage_id,
            version=version,
            parent_artifact_ids=parent_ids,
            producer=producer,
            workspace_id=self.workspace_id,
        )
        record_path = self.records_root / f"{run_id}--{stage_id}--{artifact_type}--v{version}.json"
        if record_path.exists():
            raise ValueError(f"artifact version already exists: {record_path.name}")
        self._atomic_write_text(record_path, json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n")
        return record

    def get(self, artifact_id: str) -> list[ArtifactRecord]:
        return [record for record in self.list_all() if record.artifact.artifact_id == artifact_id]

    def history(self, run_id: str, stage_id: str, artifact_type: str | None = None) -> list[ArtifactRecord]:
        run_id = _safe(run_id, "run_id")
        stage_id = _safe(stage_id, "stage_id")
        records = [
            record
            for record in self.list_all()
            if record.run_id == run_id and record.stage_id == stage_id
            and (artifact_type is None or record.artifact.artifact_type == artifact_type)
        ]
        return sorted(records, key=lambda item: item.version)

    def ancestors(self, artifact_id: str) -> list[ArtifactRecord]:
        seen: set[str] = set()
        ordered: list[ArtifactRecord] = []

        def visit(current_id: str) -> None:
            if current_id in seen:
                return
            seen.add(current_id)
            matches = self.get(current_id)
            for record in matches:
                for parent_id in record.parent_artifact_ids:
                    visit(parent_id)
                ordered.append(record)

        visit(artifact_id)
        return [record for record in ordered if record.artifact.artifact_id != artifact_id]

    def list_all(self) -> list[ArtifactRecord]:
        records: list[ArtifactRecord] = []
        for path in sorted(self.records_root.glob("*.json")):
            record = ArtifactRecord.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if record.workspace_id != self.workspace_id:
                raise ValueError("artifact belongs to a different workspace")
            records.append(record)
        return records

    def _next_version(self, run_id: str, stage_id: str, artifact_type: str) -> int:
        history = self.history(run_id, stage_id, artifact_type)
        return (history[-1].version + 1) if history else 1

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        FileArtifactCatalog._atomic_write_bytes(path, content.encode("utf-8"))

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _safe(value: str, field_name: str) -> str:
    safe = value.strip()
    if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
        raise ValueError(f"{field_name} must be a safe identifier")
    return safe
