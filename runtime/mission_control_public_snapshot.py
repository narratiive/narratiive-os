from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from runtime.mission_control_domains import MissionControlDomainRegistry


class SerializableSnapshot(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class MissionControlPublicSnapshot:
    """Workspace-scoped, presentation-neutral Mission Control read model."""

    workspace_id: str
    snapshot: Mapping[str, Any]
    domains: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        workspace_id = self.workspace_id.strip()
        if not workspace_id:
            raise ValueError("Mission Control public snapshots require a workspace_id")
        if not isinstance(self.snapshot, Mapping):
            raise TypeError("Mission Control snapshot payload must be an object")
        if not isinstance(self.domains, Mapping):
            raise TypeError("Mission Control domain payload must be an object")
        object.__setattr__(self, "workspace_id", workspace_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "snapshot": dict(self.snapshot),
            "domains": {
                name: dict(value)
                for name, value in self.domains.items()
            },
        }


class MissionControlPublicSnapshotBuilder:
    """Build a deterministic public snapshot without creating a new source of truth."""

    def __init__(
        self,
        *,
        workspace_id: str,
        domain_registry: MissionControlDomainRegistry | None = None,
    ) -> None:
        canonical_workspace = workspace_id.strip()
        if not canonical_workspace:
            raise ValueError("workspace_id must not be empty")
        self.workspace_id = canonical_workspace
        self.domain_registry = domain_registry or MissionControlDomainRegistry()

    def build(
        self,
        *,
        requested_workspace_id: str,
        snapshot: SerializableSnapshot,
        domain_values: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> MissionControlPublicSnapshot:
        requested_workspace = requested_workspace_id.strip()
        if not requested_workspace:
            raise ValueError("requested_workspace_id must not be empty")
        if requested_workspace != self.workspace_id:
            raise ValueError("workspace mismatch")

        payload = snapshot.to_dict()
        if not isinstance(payload, dict):
            raise TypeError("snapshot must serialize to an object")

        domains = self.domain_registry.to_dict(domain_values)
        return MissionControlPublicSnapshot(
            workspace_id=self.workspace_id,
            snapshot=payload,
            domains=domains,
        )
