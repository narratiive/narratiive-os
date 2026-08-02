from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from runtime.mission_control_domains import MissionControlDomainRegistry


class SerializableSnapshot(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("Mission Control snapshots require finite numeric values")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError("Mission Control snapshots must contain only serializable values")


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


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
        object.__setattr__(self, "snapshot", _freeze_value(self.snapshot))
        object.__setattr__(self, "domains", _freeze_value(self.domains))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "snapshot": _thaw_value(self.snapshot),
            "domains": _thaw_value(self.domains),
        }

    def to_json(self) -> str:
        """Return stable, standards-compliant JSON for presentation adapters."""

        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


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
