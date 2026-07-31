from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from runtime.mission_control_public_snapshot import (
    MissionControlPublicSnapshot,
    MissionControlPublicSnapshotBuilder,
)


class SerializableSnapshot(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


SnapshotLoader = Callable[[str], SerializableSnapshot]
DomainValuesLoader = Callable[[str], Mapping[str, Mapping[str, Any]] | None]


class MissionControlGatewayLoader:
    """Build the canonical public Mission Control payload for the gateway read action."""

    def __init__(
        self,
        *,
        workspace_id: str,
        snapshot_loader: SnapshotLoader,
        domain_values_loader: DomainValuesLoader,
        builder: MissionControlPublicSnapshotBuilder | None = None,
    ) -> None:
        canonical_workspace = workspace_id.strip()
        if not canonical_workspace:
            raise ValueError("workspace_id must not be empty")
        if not callable(snapshot_loader):
            raise TypeError("snapshot_loader must be callable")
        if not callable(domain_values_loader):
            raise TypeError("domain_values_loader must be callable")

        self.workspace_id = canonical_workspace
        self.snapshot_loader = snapshot_loader
        self.domain_values_loader = domain_values_loader
        self.builder = builder or MissionControlPublicSnapshotBuilder(
            workspace_id=canonical_workspace
        )

    def __call__(self, requested_workspace_id: str) -> MissionControlPublicSnapshot:
        requested_workspace = requested_workspace_id.strip()
        if not requested_workspace:
            raise ValueError("requested_workspace_id must not be empty")
        if requested_workspace != self.workspace_id:
            raise ValueError("workspace mismatch")

        snapshot = self.snapshot_loader(self.workspace_id)
        domain_values = self.domain_values_loader(self.workspace_id)
        if domain_values is not None and not isinstance(domain_values, Mapping):
            raise TypeError("domain values must be an object")

        return self.builder.build(
            requested_workspace_id=requested_workspace,
            snapshot=snapshot,
            domain_values=domain_values,
        )
