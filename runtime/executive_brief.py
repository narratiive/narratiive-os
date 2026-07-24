from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runtime.executive_message import ExecutiveMessage
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus
from runtime.mission_control_service import MissionControlService


class BriefPeriod(str, Enum):
    MORNING = "morning"
    EVENING = "evening"


@dataclass(frozen=True)
class ExecutiveBrief:
    period: BriefPeriod
    generated_at: str
    status: str
    priorities: tuple[str, ...]
    completed: tuple[str, ...]
    open_items: tuple[str, ...]
    blockers: tuple[str, ...]
    approvals: tuple[str, ...]
    executive: ExecutiveMessage

    def to_dict(self) -> dict[str, object]:
        return {
            "period": self.period.value,
            "generated_at": self.generated_at,
            "status": self.status,
            "priorities": list(self.priorities),
            "completed": list(self.completed),
            "open_items": list(self.open_items),
            "blockers": list(self.blockers),
            "approvals": list(self.approvals),
            "executive": self.executive.to_dict(),
        }

    def render_compact(self, limit: int = 3500) -> str:
        heading = "Morning brief" if self.period is BriefPeriod.MORNING else "End-of-day review"
        lines = [f"{heading} — {self.status}", self.executive.render_compact()]

        if self.period is BriefPeriod.MORNING:
            self._append(lines, "Priorities", self.priorities)
        else:
            self._append(lines, "Completed", self.completed)
            self._append(lines, "Still open", self.open_items)

        self._append(lines, "Blockers", self.blockers)
        self._append(lines, "Approvals", self.approvals)

        output = "\n".join(lines)
        if len(output) <= limit:
            return output
        return output[: limit - 1].rstrip() + "…"

    @staticmethod
    def _append(lines: list[str], heading: str, values: tuple[str, ...]) -> None:
        if not values:
            return
        lines.append(f"{heading}:")
        lines.extend(f"- {value}" for value in values)


class ExecutiveBriefService:
    """Create compact daily briefs from recorded Mission Control state only."""

    PRIORITY_LIMIT = 3
    ITEM_LIMIT = 5

    def __init__(self, mission_control: MissionControlService | None = None) -> None:
        self._mission_control = mission_control or MissionControlService()

    def build(self, snapshot: MissionControlSnapshot, period: BriefPeriod) -> ExecutiveBrief:
        executive = self._mission_control.respond(snapshot).executive
        ordered = sorted(snapshot.workstreams, key=self._priority_key)

        priorities = tuple(self._work_line(item) for item in ordered[: self.PRIORITY_LIMIT])
        completed = tuple(
            self._completion_line(item)
            for item in snapshot.workstreams
            if item.state in {"tested", "used"}
        )[: self.ITEM_LIMIT]
        open_items = tuple(
            self._work_line(item)
            for item in ordered
            if item.state not in {"tested", "used"}
        )[: self.ITEM_LIMIT]

        return ExecutiveBrief(
            period=period,
            generated_at=snapshot.generated_at,
            status=snapshot.status,
            priorities=priorities if period is BriefPeriod.MORNING else (),
            completed=completed if period is BriefPeriod.EVENING else (),
            open_items=open_items if period is BriefPeriod.EVENING else (),
            blockers=tuple(snapshot.blockers[: self.ITEM_LIMIT]),
            approvals=tuple(snapshot.approvals_required[: self.ITEM_LIMIT]),
            executive=executive,
        )

    @staticmethod
    def _priority_key(item: WorkstreamStatus) -> tuple[int, str]:
        rank = {
            "blocked": 0,
            "functional": 1,
            "known": 2,
            "unknown": 3,
            "tested": 4,
            "used": 5,
        }
        return rank[item.state], item.workstream_id

    @staticmethod
    def _work_line(item: WorkstreamStatus) -> str:
        suffix = f" [blocked: {item.blocker}]" if item.blocker else ""
        return f"{item.title} ({item.owner}) — {item.next_action}{suffix}"

    @staticmethod
    def _completion_line(item: WorkstreamStatus) -> str:
        evidence = f" — {item.evidence[0]}" if item.evidence else ""
        return f"{item.title}: {item.state}{evidence}"
