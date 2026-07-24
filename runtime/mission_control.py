from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from runtime.progress_engine import ProgressSnapshot


VALID_CONNECTION_STATES = {"connected", "not_connected", "unknown", "degraded"}
VALID_WORK_STATES = {"known", "functional", "tested", "used", "blocked", "unknown"}


@dataclass(frozen=True)
class ConnectionStatus:
    name: str
    state: str
    evidence: str | None = None
    last_checked_at: str | None = None

    def __post_init__(self) -> None:
        if self.state not in VALID_CONNECTION_STATES:
            raise ValueError(f"Unsupported connection state: {self.state}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkstreamStatus:
    workstream_id: str
    title: str
    state: str
    owner: str
    next_action: str
    evidence: tuple[str, ...] = ()
    blocker: str | None = None
    last_updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.state not in VALID_WORK_STATES:
            raise ValueError(f"Unsupported workstream state: {self.state}")
        if self.state == "blocked" and not self.blocker:
            raise ValueError("Blocked workstreams require a blocker")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionControlSnapshot:
    generated_at: str
    status: str
    progress: dict[str, Any]
    workstreams: tuple[WorkstreamStatus, ...]
    connections: tuple[ConnectionStatus, ...]
    approvals_required: tuple[str, ...]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "progress": self.progress,
            "workstreams": [item.to_dict() for item in self.workstreams],
            "connections": [item.to_dict() for item in self.connections],
            "approvals_required": list(self.approvals_required),
            "blockers": list(self.blockers),
        }


class MissionControlBuilder:
    """Build one evidence-backed, read-only view of Narratiive OS state."""

    def build(
        self,
        *,
        generated_at: str,
        progress: ProgressSnapshot,
        workstreams: Iterable[WorkstreamStatus] = (),
        connections: Mapping[str, Mapping[str, Any]] | None = None,
        approvals_required: Iterable[str] = (),
    ) -> MissionControlSnapshot:
        workstream_items = tuple(sorted(workstreams, key=lambda item: item.workstream_id))
        connection_items = self._connections(connections or {})
        blockers = self._blockers(progress, workstream_items, connection_items)

        if blockers:
            status = "blocked"
        elif progress.status == "empty" and not workstream_items:
            status = "empty"
        elif any(item.state in {"unknown", "not_connected", "degraded"} for item in connection_items):
            status = "partial"
        else:
            status = "healthy"

        return MissionControlSnapshot(
            generated_at=generated_at,
            status=status,
            progress=progress.to_dict(),
            workstreams=workstream_items,
            connections=connection_items,
            approvals_required=tuple(sorted(set(approvals_required))),
            blockers=blockers,
        )

    @staticmethod
    def _connections(values: Mapping[str, Mapping[str, Any]]) -> tuple[ConnectionStatus, ...]:
        items: list[ConnectionStatus] = []
        for name in sorted(values):
            payload = values[name]
            state = str(payload.get("state", "unknown"))
            items.append(
                ConnectionStatus(
                    name=name,
                    state=state,
                    evidence=MissionControlBuilder._optional_text(payload.get("evidence")),
                    last_checked_at=MissionControlBuilder._optional_text(
                        payload.get("last_checked_at")
                    ),
                )
            )
        return tuple(items)

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _blockers(
        progress: ProgressSnapshot,
        workstreams: tuple[WorkstreamStatus, ...],
        connections: tuple[ConnectionStatus, ...],
    ) -> tuple[str, ...]:
        blockers: set[str] = set()

        for finding in progress.validation.errors:
            blockers.add(f"repository:{finding.code}")

        for item in workstreams:
            if item.state == "blocked" and item.blocker:
                blockers.add(f"workstream:{item.workstream_id}:{item.blocker}")

        for item in connections:
            if item.state == "degraded":
                blockers.add(f"connection:{item.name}:degraded")

        return tuple(sorted(blockers))
