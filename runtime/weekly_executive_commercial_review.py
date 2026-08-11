from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from runtime.client_intelligence import ClientPortfolioSnapshot
from runtime.closed_loop_execution import ExecutionRecord
from runtime.commercial_intelligence import CommercialSnapshot


@dataclass(frozen=True, slots=True)
class WeeklyExecutiveCommercialReview:
    pipeline_value: Decimal
    weighted_pipeline_value: Decimal
    open_opportunities: int
    stalled_opportunities: int
    active_clients: int
    client_revenue_value: Decimal
    at_risk_clients: int
    watch_clients: int
    completed_work: int
    unresolved_work: int
    escalated_work: int
    wins: tuple[str, ...]
    risks: tuple[str, ...]
    priorities: tuple[str, ...]

    def render(self, *, max_items_per_section: int = 3) -> str:
        if max_items_per_section < 1:
            raise ValueError("max_items_per_section must be positive")

        lines = [
            "Weekly executive review",
            (
                f"Commercial: {self.open_opportunities} open opportunities, "
                f"£{self.weighted_pipeline_value:,.2f} weighted pipeline "
                f"(£{self.pipeline_value:,.2f} total)."
            ),
            (
                f"Clients: {self.active_clients} active, £{self.client_revenue_value:,.2f} value, "
                f"{self.at_risk_clients} at risk, {self.watch_clients} on watch."
            ),
            (
                f"Execution: {self.completed_work} completed, {self.unresolved_work} unresolved, "
                f"{self.escalated_work} escalated."
            ),
        ]
        lines.extend(self._section("Wins", self.wins, max_items_per_section))
        lines.extend(self._section("Risks", self.risks, max_items_per_section))
        lines.extend(self._section("Next week", self.priorities, max_items_per_section))
        return "\n".join(lines)

    @staticmethod
    def _section(title: str, items: tuple[str, ...], limit: int) -> tuple[str, ...]:
        if not items:
            return (f"{title}: none recorded.",)
        return (f"{title}:", *(f"- {item}" for item in items[:limit]))


class WeeklyExecutiveCommercialReviewBuilder:
    """Combine commercial, client and execution state into a bounded CEO review."""

    def build(
        self,
        commercial: CommercialSnapshot,
        clients: ClientPortfolioSnapshot,
        execution_records: Iterable[ExecutionRecord],
    ) -> WeeklyExecutiveCommercialReview:
        records = tuple(execution_records)
        task_ids = [record.task_id for record in records]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("duplicate execution task_id")

        completed = tuple(record for record in records if record.status == "completed")
        unresolved = tuple(record for record in records if record.status != "completed")
        escalated = tuple(record for record in records if record.status == "escalated")

        wins = tuple(
            f"Completed {record.task_id} ({record.capability})"
            for record in sorted(completed, key=lambda item: (-item.priority_score, item.task_id))
        )

        risks: list[str] = []
        risks.extend(
            f"Stalled opportunity: {item.account_name} — {item.next_action or 're-engage'}"
            for item in commercial.stalled_opportunities
        )
        risks.extend(
            f"Client at risk: {item.name} — {item.next_action}"
            for item in clients.at_risk_clients
        )
        risks.extend(
            f"Escalated execution: {record.task_id} — {record.blocker or 'requires intervention'}"
            for record in sorted(escalated, key=lambda item: (-item.priority_score, item.task_id))
        )

        priorities: list[str] = []
        priorities.extend(commercial.actions_required)
        priorities.extend(clients.actions_required)
        priorities.extend(
            f"Resolve {record.task_id}: {record.blocker or 'complete outstanding work'}"
            for record in sorted(unresolved, key=lambda item: (-item.priority_score, item.task_id))
            if record.status in {"blocked", "failed", "escalated"}
        )
        priorities = self._deduplicate(priorities)

        if not priorities:
            if commercial.open_opportunities == 0:
                priorities.append("Create new qualified commercial opportunities")
            elif clients.active_clients == 0:
                priorities.append("Convert the strongest opportunity into an active client")
            else:
                priorities.append("Protect client momentum and advance the highest-value opportunity")

        return WeeklyExecutiveCommercialReview(
            pipeline_value=commercial.pipeline_value,
            weighted_pipeline_value=commercial.weighted_pipeline_value,
            open_opportunities=commercial.open_opportunities,
            stalled_opportunities=len(commercial.stalled_opportunities),
            active_clients=clients.active_clients,
            client_revenue_value=clients.revenue_value,
            at_risk_clients=len(clients.at_risk_clients),
            watch_clients=len(clients.watch_clients),
            completed_work=len(completed),
            unresolved_work=len(unresolved),
            escalated_work=len(escalated),
            wins=wins,
            risks=tuple(self._deduplicate(risks)),
            priorities=tuple(priorities),
        )

    @staticmethod
    def _deduplicate(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            clean = item.strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
        return result
