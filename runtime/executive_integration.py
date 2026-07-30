from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from runtime.executive_brief import BriefPeriod, ExecutiveBrief, ExecutiveBriefService
from runtime.executive_memory import ExecutiveMemoryStore, MemoryKind, MemoryScope
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus


class ExecutivePriorityEngine:
    """Rank work by business impact before technical state.

    Workstream schemas do not yet carry an explicit business domain, so the
    engine uses deterministic title/id/action evidence. Unknown work falls
    back to engineering rather than being promoted above client or revenue work.
    """

    DOMAIN_RANK = {
        "client": 0,
        "revenue": 1,
        "delivery": 2,
        "automation": 3,
        "engineering": 4,
        "infrastructure": 5,
    }
    STATE_RANK = {
        "blocked": 0,
        "functional": 1,
        "known": 2,
        "unknown": 3,
        "tested": 4,
        "used": 5,
    }
    KEYWORDS = {
        "client": ("client", "customer", "campaign", "account"),
        "revenue": ("revenue", "sales", "lead", "pipeline", "proposal", "outreach"),
        "delivery": ("delivery", "deliverable", "brief", "newsletter", "content", "launch"),
        "automation": ("automation", "workflow", "n8n", "make", "telegram"),
        "infrastructure": ("infrastructure", "runtime", "bridge", "health", "credential", "deployment"),
        "engineering": ("github", "repository", "pull request", "pr ", "code", "test", "merge"),
    }

    @classmethod
    def domain(cls, item: WorkstreamStatus) -> str:
        evidence = " ".join(
            (
                item.workstream_id,
                item.title,
                item.next_action,
                item.blocker or "",
                *item.evidence,
            )
        ).casefold()
        for domain in ("client", "revenue", "delivery", "automation", "infrastructure", "engineering"):
            if any(keyword in evidence for keyword in cls.KEYWORDS[domain]):
                return domain
        return "engineering"

    @classmethod
    def key(cls, item: WorkstreamStatus) -> tuple[int, int, str]:
        return (
            cls.DOMAIN_RANK[cls.domain(item)],
            cls.STATE_RANK[item.state],
            item.workstream_id,
        )


class ExecutiveChangeFilter:
    """Remove repeated or empty lines while preserving evidence order."""

    @staticmethod
    def unique(values: Iterable[str], *, limit: int) -> tuple[str, ...]:
        seen: set[str] = set()
        output: list[str] = []
        for raw in values:
            value = " ".join(str(raw).split())
            key = value.casefold()
            if not value or key in seen:
                continue
            seen.add(key)
            output.append(value)
            if len(output) >= limit:
                break
        return tuple(output)


class ExecutiveMemoryIntegration:
    """Select and record durable continuity for executive brief generation."""

    RECALL_KINDS = (
        MemoryKind.DECISION,
        MemoryKind.COMMITMENT,
        MemoryKind.APPROVAL,
        MemoryKind.CONTEXT,
        MemoryKind.OUTCOME,
    )

    def __init__(
        self,
        store: ExecutiveMemoryStore,
        *,
        scope: MemoryScope | None = None,
    ) -> None:
        self.store = store
        self.scope = scope or MemoryScope()

    def recall(self, *, limit: int = 8) -> tuple[str, ...]:
        records = self.store.select(
            scope=self.scope,
            kinds=self.RECALL_KINDS,
            minimum_importance=3,
            limit=limit,
        )
        return tuple(self._line(record.kind, record.summary) for record in records)

    def approvals(self, *, limit: int = 5) -> tuple[str, ...]:
        records = self.store.select(
            scope=self.scope,
            kinds=(MemoryKind.APPROVAL, MemoryKind.DECISION, MemoryKind.COMMITMENT),
            minimum_importance=3,
            requires_matt=True,
            limit=limit,
        )
        return tuple(self._line(record.kind, record.summary) for record in records)

    def capture(self, brief: ExecutiveBrief) -> None:
        summary = (
            f"{brief.period.value} executive brief generated: "
            f"{len(brief.changed)} changes, {len(brief.blockers)} blockers, "
            f"{len(brief.approvals)} approvals"
        )
        existing = self.store.select(
            scope=self.scope,
            kinds=(MemoryKind.OUTCOME,),
            minimum_importance=1,
            limit=1,
        )
        if existing and existing[0].summary == summary:
            return
        self.store.append(
            kind=MemoryKind.OUTCOME,
            summary=summary,
            detail=brief.executive.recommendation,
            scope=self.scope,
            source="executive_brief",
            importance=3,
        )

    @staticmethod
    def _line(kind: MemoryKind, summary: str) -> str:
        return f"Memory — {kind.value}: {summary}"


class IntegratedExecutiveBriefService(ExecutiveBriefService):
    """Business-first executive brief service used by live Tony commands."""

    def __init__(
        self,
        mission_control=None,
        *,
        memory: ExecutiveMemoryIntegration | None = None,
    ) -> None:
        super().__init__(mission_control)
        self._memory = memory

    def build(self, snapshot: MissionControlSnapshot, period: BriefPeriod) -> ExecutiveBrief:
        brief = super().build(snapshot, period)
        ordered = sorted(snapshot.workstreams, key=ExecutivePriorityEngine.key)
        active = tuple(item for item in ordered if item.state not in {"tested", "used", "unknown"})
        recalled = self._memory.recall() if self._memory is not None else ()
        recalled_approvals = self._memory.approvals() if self._memory is not None else ()

        priorities = ExecutiveChangeFilter.unique(
            (
                *(self._work_line(item) for item in active),
                *(recalled if period is BriefPeriod.MORNING else ()),
            ),
            limit=self.PRIORITY_LIMIT,
        )
        open_items = ExecutiveChangeFilter.unique(
            (
                *(self._work_line(item) for item in active),
                *(recalled if period is BriefPeriod.EVENING else ()),
            ),
            limit=self.ITEM_LIMIT,
        )
        tony_handling = ExecutiveChangeFilter.unique(
            (
                self._work_line(item)
                for item in active
                if item.owner.strip().casefold() == "tony"
            ),
            limit=self.ITEM_LIMIT,
        )
        carry_forward = ExecutiveChangeFilter.unique(
            (
                *(self._work_line(item) for item in active if item.state in {"blocked", "known", "functional"}),
                *(recalled if period is BriefPeriod.EVENING else ()),
            ),
            limit=self.PRIORITY_LIMIT,
        )

        integrated = replace(
            brief,
            priorities=priorities if period is BriefPeriod.MORNING else (),
            open_items=open_items if period is BriefPeriod.EVENING else (),
            changed=ExecutiveChangeFilter.unique(brief.changed, limit=self.ITEM_LIMIT),
            blockers=ExecutiveChangeFilter.unique(brief.blockers, limit=self.ITEM_LIMIT),
            approvals=ExecutiveChangeFilter.unique(
                (*recalled_approvals, *brief.approvals),
                limit=self.ITEM_LIMIT,
            ),
            tony_handling=tony_handling if period is BriefPeriod.MORNING else (),
            carry_forward=carry_forward if period is BriefPeriod.EVENING else (),
            system_watchouts=ExecutiveChangeFilter.unique(
                brief.system_watchouts, limit=self.ITEM_LIMIT
            ),
        )
        if self._memory is not None:
            self._memory.capture(integrated)
        return integrated
