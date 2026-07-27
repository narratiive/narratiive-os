from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from runtime.engineering_handoff import EngineeringHandoffSnapshot
from runtime.engineering_orchestrator import EngineeringRunSnapshot
from runtime.github_work import GitHubWorkSnapshot
from runtime.progress_engine import ProgressSnapshot


VALID_CONNECTION_STATES = {"connected", "not_connected", "unknown", "degraded"}
VALID_WORK_STATES = {"known", "functional", "tested", "used", "blocked", "unknown"}
VALID_FOCUS_CATEGORIES = {"blocker", "approval", "risk", "opportunity", "workstream"}
VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}


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
class ExecutiveFocusItem:
    action: str
    category: str
    evidence: tuple[str, ...]
    confidence: str = "high"

    def __post_init__(self) -> None:
        if self.category not in VALID_FOCUS_CATEGORIES:
            raise ValueError(f"Unsupported focus category: {self.category}")
        if self.confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(f"Unsupported focus confidence: {self.confidence}")
        if not self.action.strip():
            raise ValueError("Focus items require an action")
        if not self.evidence or any(not item.strip() for item in self.evidence):
            raise ValueError("Focus items require non-empty evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "category": self.category,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


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
    recommended_focus_details: tuple[ExecutiveFocusItem, ...] = ()
    recent_wins: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    opportunities: tuple[str, ...] = ()

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
            "recommended_focus_details": [
                item.to_dict() for item in self.recommended_focus_details
            ],
            "recent_wins": list(self.recent_wins),
            "risks": list(self.risks),
            "opportunities": list(self.opportunities),
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
        recent_wins: Iterable[str] = (),
        risks: Iterable[str] = (),
        opportunities: Iterable[str] = (),
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
        risk_items = self._explicit_items(risks)
        opportunity_items = self._explicit_items(opportunities)
        focus_details = self._recommended_focus_details(
            blockers,
            approval_items,
            risk_items,
            opportunity_items,
            workstream_items,
        )
        recommended_focus = tuple(item.action for item in focus_details)
        win_items = self._recent_wins(recent_wins)

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
            recommended_focus_details=focus_details,
            recent_wins=win_items,
            risks=risk_items,
            opportunities=opportunity_items,
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
    def _recent_wins(values: Iterable[str], *, limit: int = 5) -> tuple[str, ...]:
        """Return explicit, evidence-ready wins without inferring completion."""
        return MissionControlBuilder._explicit_items(values, limit=limit)

    @staticmethod
    def _explicit_items(values: Iterable[str], *, limit: int = 5) -> tuple[str, ...]:
        """Normalise bounded executive inputs without inferring missing state."""
        if limit < 1:
            return ()
        items = {str(value).strip() for value in values if str(value).strip()}
        return tuple(sorted(items)[:limit])

    @staticmethod
    def _recommended_focus_details(
        blockers: tuple[str, ...],
        approvals: tuple[str, ...],
        risks: tuple[str, ...],
        opportunities: tuple[str, ...],
        workstreams: tuple[WorkstreamStatus, ...],
        *,
        limit: int = 3,
    ) -> tuple[ExecutiveFocusItem, ...]:
        """Return bounded focus items with canonical evidence and confidence."""
        if limit < 1:
            return ()

        focus: list[ExecutiveFocusItem] = []
        seen: set[str] = set()

        def add(
            action: str,
            *,
            category: str,
            evidence: Iterable[str],
            confidence: str = "high",
        ) -> None:
            item = action.strip()
            evidence_items = tuple(
                dict.fromkeys(value.strip() for value in evidence if value.strip())
            )
            if (
                item
                and item not in seen
                and len(focus) < limit
                and evidence_items
            ):
                seen.add(item)
                focus.append(
                    ExecutiveFocusItem(
                        action=item,
                        category=category,
                        evidence=evidence_items,
                        confidence=confidence,
                    )
                )

        for index, blocker in enumerate(blockers):
            add(
                f"resolve:{blocker}",
                category="blocker",
                evidence=(f"blockers/{index}",),
            )
        for index, approval in enumerate(approvals):
            add(
                f"decide:{approval}",
                category="approval",
                evidence=(f"approvals_required/{index}",),
            )
        for index, risk in enumerate(risks):
            add(
                f"mitigate:{risk}",
                category="risk",
                evidence=(f"risks/{index}",),
            )
        for index, opportunity in enumerate(opportunities):
            add(
                f"pursue:{opportunity}",
                category="opportunity",
                evidence=(f"opportunities/{index}",),
            )
        for index, workstream in enumerate(workstreams):
            if workstream.state != "blocked":
                add(
                    f"advance:{workstream.workstream_id}:{workstream.next_action.strip()}",
                    category="workstream",
                    evidence=(
                        f"workstreams/{index}",
                        *workstream.evidence,
                    ),
                )

        return tuple(focus)

    @staticmethod
    def _recommended_focus(
        blockers: tuple[str, ...],
        approvals: tuple[str, ...],
        risks: tuple[str, ...],
        opportunities: tuple[str, ...],
        workstreams: tuple[WorkstreamStatus, ...],
        *,
        limit: int = 3,
    ) -> tuple[str, ...]:
        """Backward-compatible string projection of the canonical focus details."""
        return tuple(
            item.action
            for item in MissionControlBuilder._recommended_focus_details(
                blockers,
                approvals,
                risks,
                opportunities,
                workstreams,
                limit=limit,
            )
        )

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
