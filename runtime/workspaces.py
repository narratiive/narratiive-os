from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from .memory import FileMemoryStore
from .repositories import FileWorkflowRunRepository, JsonlEventLog

if TYPE_CHECKING:
    from .composition import RuntimeComponents


LEGACY_WORKSPACE_ID = "legacy"


class WorkspaceNotFound(KeyError):
    """Raised when a workspace identity is unknown."""


class CrossWorkspaceReference(ValueError):
    """Raised when a request references data owned by another workspace."""


@dataclass(frozen=True, slots=True)
class Workspace:
    workspace_id: str
    client_id: str
    display_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        _safe(self.workspace_id, "workspace_id")
        _safe(self.client_id, "client_id")
        if not self.display_name.strip():
            raise ValueError("display_name must not be empty")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workspace":
        return cls(
            workspace_id=str(data["workspace_id"]),
            client_id=str(data["client_id"]),
            display_name=str(data["display_name"]),
            created_at=str(data["created_at"]),
        )


class FileWorkspaceRepository:
    """Atomic workspace registry with one physical data root per client."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create(self, workspace: Workspace) -> Workspace:
        path = self._metadata_path(workspace.workspace_id)
        with self._lock:
            if path.exists():
                existing = self.get(workspace.workspace_id)
                if (
                    existing.client_id == workspace.client_id
                    and existing.display_name == workspace.display_name
                ):
                    return existing
                raise ValueError(
                    f"workspace already exists: {workspace.workspace_id}"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(
                path,
                json.dumps(workspace.to_dict(), indent=2, sort_keys=True) + "\n",
            )
        return workspace

    def get(self, workspace_id: str) -> Workspace:
        path = self._metadata_path(workspace_id)
        if not path.is_file():
            raise WorkspaceNotFound(workspace_id)
        return Workspace.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> tuple[Workspace, ...]:
        workspaces = []
        for path in sorted(self.root.glob("*/workspace.json")):
            workspaces.append(
                Workspace.from_dict(json.loads(path.read_text(encoding="utf-8")))
            )
        return tuple(workspaces)

    def path(self, workspace_id: str) -> Path:
        self.get(workspace_id)
        return self.root / _safe(workspace_id, "workspace_id")

    def _metadata_path(self, workspace_id: str) -> Path:
        return self.root / _safe(workspace_id, "workspace_id") / "workspace.json"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class WorkspaceRuntimeManager:
    """Composes isolated runtimes and locates cross-workspace references."""

    def __init__(self, runtime_root: str | Path, repository_root: str | Path) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.repository_root = Path(repository_root).resolve()
        self.repository = FileWorkspaceRepository(self.runtime_root / "workspaces")

    def create(
        self,
        workspace_id: str,
        client_id: str,
        display_name: str,
    ) -> Workspace:
        return self.repository.create(
            Workspace(workspace_id, client_id, display_name)
        )

    def runtime(self, workspace_id: str) -> "RuntimeComponents":
        from .composition import compose_workspace_runtime

        workspace = self.repository.get(workspace_id)
        return compose_workspace_runtime(
            self.runtime_root,
            self.repository_root,
            workspace,
            workspace_repository=self.repository,
        )

    def locate_run(self, run_id: str) -> str | None:
        _safe(run_id, "run_id")
        owners = [
            workspace.workspace_id
            for workspace in self.repository.list()
            if (self.repository.path(workspace.workspace_id) / "runs" / f"{run_id}.json").is_file()
        ]
        return owners[0] if owners else None

    def migrate_legacy(
        self,
        *,
        workspace_id: str,
        client_id: str,
        display_name: str,
    ) -> Workspace:
        """Copy legacy unscoped data into a workspace without deleting the source."""

        workspace = self.create(workspace_id, client_id, display_name)
        target = self.repository.path(workspace_id)

        legacy_runs = FileWorkflowRunRepository(self.runtime_root / "runs")
        scoped_runs = FileWorkflowRunRepository(
            target / "runs",
            workspace_id=workspace_id,
            client_id=client_id,
        )
        for run_id in legacy_runs.list_run_ids():
            if scoped_runs.exists(run_id):
                continue
            state = legacy_runs.load(run_id)
            state.workspace_id = workspace_id
            state.client_id = client_id
            scoped_runs.save(state)

        legacy_events = JsonlEventLog(self.runtime_root / "events")
        scoped_events = JsonlEventLog(
            target / "events", workspace_id=workspace_id
        )
        for run_id in legacy_runs.list_run_ids():
            if scoped_events.read(run_id):
                continue
            for event in legacy_events.read(run_id):
                scoped_events.append(replace(event, workspace_id=workspace_id))

        self._migrate_memory(target, workspace_id, client_id)
        self._copy_tree("jobs", target)
        self._copy_tree("artifacts", target)
        self._copy_tree("artifact-catalog/content", target)
        self._copy_json_records(
            "artifact-catalog/records",
            target,
            workspace_id,
            artifact=True,
        )
        self._copy_json_records(
            "prompts/versions", target, workspace_id
        )
        self._copy_tree("prompts/active", target)
        return workspace

    def _migrate_memory(
        self,
        target: Path,
        workspace_id: str,
        client_id: str,
    ) -> None:
        legacy = FileMemoryStore(self.runtime_root / "memory")
        source_path = self.runtime_root / "memory" / f"{client_id}.jsonl"
        if not source_path.is_file():
            return
        scoped = FileMemoryStore(
            target / "memory",
            workspace_id=workspace_id,
            client_id=client_id,
        )
        for record in legacy._read_all(client_id):
            if scoped.contains(client_id, record.memory_id):
                continue
            scoped.append(
                replace(
                    record,
                    workspace_id=workspace_id,
                    sequence=0,
                    previous_checksum="",
                    checksum="",
                )
            )

    def _copy_tree(self, relative: str, target: Path) -> None:
        source = self.runtime_root / relative
        if source.is_dir():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)

    def _copy_json_records(
        self,
        relative: str,
        target: Path,
        workspace_id: str,
        *,
        artifact: bool = False,
    ) -> None:
        source = self.runtime_root / relative
        destination = target / relative
        if not source.is_dir():
            return
        destination.mkdir(parents=True, exist_ok=True)
        for path in source.glob("*.json"):
            output = destination / path.name
            if output.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["workspace_id"] = workspace_id
            if artifact:
                payload["artifact"].setdefault("metadata", {})[
                    "workspace_id"
                ] = workspace_id
            FileWorkspaceRepository._atomic_write(
                output,
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
            )


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
