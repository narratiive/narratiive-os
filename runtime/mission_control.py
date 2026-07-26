from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from runtime.engineering_handoff import EngineeringHandoffSnapshot
from runtime.engineering_orchestrator import EngineeringRunSnapshot
from runtime.github_work import GitHubWorkSnapshot
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
    github_work: GitHubWorkSnapshot | None = None
    engineering_handoffs: tuple[EngineeringHandoffSnapshot, ...] = ()
    engineering_runs: tuple[EngineeringRunSnapshot, ...] = ()
    recommended_focus: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "progress": self.progress,
            "workstreams": [item.to_dict() for item in self.workstreams],
            "connections": [item.to_dict() for item in self.connections],
            "approvals_required": list(self.approvals_required),
            "blockers": list(self.blockers),
            "github_work": (
                self.github_work.to_dict() if self.github_work is not None else None
            ),
            "engineering_handoffs": [
                item.to_dict() for item in self.engineering_handoffs
            ],
            "engineering_runs": [
                item.to_dict() for item in self.engineering_runs
            ],
            "recommended_focus": list(self.recommended_focus),
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
        github_work: GitHubWorkSnapshot | None = None,
        engineering_handoffs: Iterable[EngineeringHandoffSnapshot] = (),
        engineering_runs: Iterable[EngineeringRunSnapshot] = (),
    ) -> MissionControlSnapshot:
        workstream_items = tuple(sorted(workstreams, key=lambda item: item.workstream_id))
        connection_items = self._connections(connections or {})
        handoff_items = tuple(
            sorted(engineering_handoffs, key=lambda item: item.task_id)
        )
        run_items = tuple(
            sorted(engineering_runs, key=lambda item: item.task_id)
        )
        approval_items = self._approvals(approvals_required, github_work)
        blockers = self._blockers(
            progress,
            workstream_items,
            connection_items,
            github_work,
            handoff_items,
            run_items,
        )
        recommended_focus = self._recommended_focus(
            blockers,
            approval_items,
            workstream_items,
        )

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
            approvals_required=approval_items,
            blockers=blockers,
            github_work=github_work,
            engineering_handoffs=handoff_items,
            engineering_runs=run_items,
            recommended_focus=recommended_focus,
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
    def _approvals(
        values: Iterable[str],
        github_work: GitHubWorkSnapshot | None,
    ) -> tuple[str, ...]:
        approvals = {str(value).strip() for value in values if str(value).strip()}
        if github_work is not None:
            for item in github_work.matt_approval_required:
                approvals.add(f"github:{item.kind}:{item.number}:{item.url}")
        return tuple(sorted(approvals))

    @staticmethod
    def _recommended_focus(
        blockers: tuple[str, ...],
        approvals: tuple[str, ...],
        workstreams: tuple[WorkstreamStatus, ...],
        *,
        limit: int = 3,
    ) -> tuple[str, ...]:
        """Return a bounded executive focus list from canonical snapshot state."""
        if limit < 1:
            return ()

        focus: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            item = value.strip()
            if item and item not in seen and len(focus) < limit:
                seen.add(item)
                focus.append(item)

        for blocker in blockers:
            add(f"resolve:{blocker}")
        for approval in approvals:
            add(f"decide:{approval}")
        for workstream in workstreams:
            if workstream.state != "blocked":
                add(f"advance:{workstream.workstream_id}:{workstream.next_action.strip()}")

        return tuple(focus)

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _blockers(
        progress: ProgressSnapshot,
        workstreams: tuple[WorkstreamStatus, ...],
        connections: tuple[ConnectionStatus, ...],
        github_work: GitHubWorkSnapshot | None = None,
        engineering_handoffs: tuple[EngineeringHandoffSnapshot, ...] = (),
        engineering_runs: tuple[EngineeringRunSnapshot, ...] = (),
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

        if github_work is not None:
            for item in github_work.blocked:
                for reason in item.blocker_reasons:
                    blockers.add(f"github:{item.kind}:{item.number}:{reason}")

        for handoff in engineering_handoffs:
            for reason in handoff.blockers:
                blockers.add(f"engineering:{handoff.task_id}:{reason}")

        for run in engineering_runs:
            for reason in run.blockers:
                blockers.add(f"engineering-execution:{run.task_id}:{reason}")

        return tuple(sorted(blockers))
