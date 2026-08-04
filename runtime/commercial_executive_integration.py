from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from runtime.commercial_intelligence import CommercialSnapshot


@dataclass(frozen=True, slots=True)
class CommercialExecutiveState:
    pipeline_value: Decimal
    weighted_pipeline_value: Decimal
    open_opportunities: int
    stalled_opportunities: int
    priorities: tuple[str, ...]

    def to_mission_control_domain(self) -> dict[str, Any]:
        evidence = [
            f"pipeline_value:{self.pipeline_value}",
            f"weighted_pipeline_value:{self.weighted_pipeline_value}",
            f"open_opportunities:{self.open_opportunities}",
            f"stalled_opportunities:{self.stalled_opportunities}",
        ]
        evidence.extend(f"priority:{item}" for item in self.priorities)
        return {
            "state": "connected",
            "evidence": evidence,
            "summary": {
                "pipeline_value": str(self.pipeline_value),
                "weighted_pipeline_value": str(self.weighted_pipeline_value),
                "open_opportunities": self.open_opportunities,
                "stalled_opportunities": self.stalled_opportunities,
                "priorities": list(self.priorities),
            },
        }

    def executive_lines(self, *, limit: int = 3) -> tuple[str, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        headline = (
            f"Commercial: {self.open_opportunities} open opportunities, "
            f"weighted pipeline £{self.weighted_pipeline_value:,.2f}."
        )
        if not self.priorities:
            return (headline, "No commercial follow-up is currently overdue.")
        return (headline, *self.priorities[:limit])


class CommercialExecutiveIntegrator:
    def integrate(self, snapshot: CommercialSnapshot) -> CommercialExecutiveState:
        if snapshot.open_opportunities < 0:
            raise ValueError("open_opportunities must not be negative")
        priorities = tuple(
            f"Commercial priority: {action.strip()}"
            for action in snapshot.actions_required
            if action.strip()
        )
        return CommercialExecutiveState(
            pipeline_value=snapshot.pipeline_value,
            weighted_pipeline_value=snapshot.weighted_pipeline_value,
            open_opportunities=snapshot.open_opportunities,
            stalled_opportunities=len(snapshot.stalled_opportunities),
            priorities=priorities,
        )
