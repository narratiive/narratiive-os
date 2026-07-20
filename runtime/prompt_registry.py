from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptVersion:
    prompt_id: str
    version: int
    content: str
    checksum: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    workspace_id: str = "legacy"

    def __post_init__(self) -> None:
        if not self.prompt_id.strip():
            raise ValueError("prompt_id must not be empty")
        if self.version <= 0:
            raise ValueError("version must be positive")
        if not self.content.strip():
            raise ValueError("content must not be empty")
        _safe(self.workspace_id)


class FilePromptRegistry:
    """Versioned prompt store with explicit activation and rollback."""

    def __init__(self, root: str | Path, *, workspace_id: str = "legacy") -> None:
        self.root = Path(root)
        self.workspace_id = _safe(workspace_id)
        self.versions_root = self.root / "versions"
        self.active_root = self.root / "active"
        self.versions_root.mkdir(parents=True, exist_ok=True)
        self.active_root.mkdir(parents=True, exist_ok=True)

    def publish(self, prompt_id: str, content: str, metadata: dict[str, Any] | None = None) -> PromptVersion:
        prompt_id = _safe(prompt_id)
        content = str(content)
        if not content.strip():
            raise ValueError("content must not be empty")
        version = self._next_version(prompt_id)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        prompt = PromptVersion(
            prompt_id=prompt_id,
            version=version,
            content=content,
            checksum=checksum,
            metadata=dict(metadata or {}),
            workspace_id=self.workspace_id,
        )
        path = self._version_path(prompt_id, version)
        self._atomic_write(path, json.dumps(asdict(prompt), indent=2, sort_keys=True) + "\n")
        return prompt

    def activate(self, prompt_id: str, version: int) -> PromptVersion:
        prompt = self.get(prompt_id, version)
        marker = {"prompt_id": prompt.prompt_id, "version": prompt.version, "checksum": prompt.checksum}
        self._atomic_write(self.active_root / f"{prompt.prompt_id}.json", json.dumps(marker, sort_keys=True) + "\n")
        return prompt

    def active(self, prompt_id: str) -> PromptVersion:
        prompt_id = _safe(prompt_id)
        path = self.active_root / f"{prompt_id}.json"
        if not path.exists():
            raise KeyError(f"no active version for prompt: {prompt_id}")
        marker = json.loads(path.read_text(encoding="utf-8"))
        prompt = self.get(prompt_id, int(marker["version"]))
        if prompt.checksum != marker["checksum"]:
            raise ValueError(f"active prompt checksum mismatch: {prompt_id}")
        return prompt

    def rollback(self, prompt_id: str) -> PromptVersion:
        current = self.active(prompt_id)
        if current.version <= 1:
            raise ValueError("no previous prompt version available")
        return self.activate(prompt_id, current.version - 1)

    def get(self, prompt_id: str, version: int) -> PromptVersion:
        prompt_id = _safe(prompt_id)
        if version <= 0:
            raise ValueError("version must be positive")
        path = self._version_path(prompt_id, version)
        if not path.exists():
            raise KeyError(f"prompt version not found: {prompt_id}@{version}")
        data = json.loads(path.read_text(encoding="utf-8"))
        prompt = PromptVersion(**data)
        if prompt.workspace_id != self.workspace_id:
            raise ValueError("prompt belongs to a different workspace")
        return prompt

    def history(self, prompt_id: str) -> list[PromptVersion]:
        prompt_id = _safe(prompt_id)
        versions: list[PromptVersion] = []
        for path in sorted(self.versions_root.glob(f"{prompt_id}--v*.json")):
            prompt = PromptVersion(**json.loads(path.read_text(encoding="utf-8")))
            if prompt.workspace_id != self.workspace_id:
                raise ValueError("prompt belongs to a different workspace")
            versions.append(prompt)
        return sorted(versions, key=lambda item: item.version)

    def _next_version(self, prompt_id: str) -> int:
        history = self.history(prompt_id)
        return history[-1].version + 1 if history else 1

    def _version_path(self, prompt_id: str, version: int) -> Path:
        return self.versions_root / f"{prompt_id}--v{version}.json"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _safe(value: str) -> str:
    safe = value.strip()
    if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
        raise ValueError("prompt_id must be a safe identifier")
    return safe
