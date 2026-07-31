from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol


class SerializableSnapshot(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


SnapshotLoader = Callable[[str], SerializableSnapshot]


class MissionControlReadAction:
    """Expose the canonical Mission Control snapshot through a read-only action boundary."""

    action = "mission_control_snapshot"

    def __init__(self, *, workspace_id: str, snapshot_loader: SnapshotLoader) -> None:
        canonical_workspace = workspace_id.strip()
        if not canonical_workspace:
            raise ValueError("workspace_id must not be empty")
        if not callable(snapshot_loader):
            raise TypeError("snapshot_loader must be callable")

        self.workspace_id = canonical_workspace
        self.snapshot_loader = snapshot_loader

    def execute(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise TypeError("request must be an object")

        action = str(request.get("action", "")).strip()
        if action != self.action:
            raise ValueError("unsupported action")

        requested_workspace = str(request.get("workspace_id", "")).strip()
        if not requested_workspace:
            raise ValueError("workspace_id must not be empty")
        if requested_workspace != self.workspace_id:
            raise ValueError("workspace mismatch")

        payload = request.get("payload")
        if payload not in (None, {}):
            raise ValueError("mission_control_snapshot does not accept payload")

        snapshot = self.snapshot_loader(requested_workspace)
        if snapshot is None or not callable(getattr(snapshot, "to_dict", None)):
            raise TypeError("snapshot loader returned an invalid snapshot")

        serialized = snapshot.to_dict()
        if not isinstance(serialized, dict):
            raise TypeError("snapshot must serialize to an object")
        if serialized.get("workspace_id") != requested_workspace:
            raise ValueError("snapshot workspace mismatch")

        return {
            "ok": True,
            "action": self.action,
            "workspace_id": requested_workspace,
            "data": serialized,
        }
