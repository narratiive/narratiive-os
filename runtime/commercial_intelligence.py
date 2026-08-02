from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Literal

PipelineStage = Literal["lead", "qualified", "proposal", "negotiation", "won", "lost"]

_STAGE_PROBABILITY: dict[PipelineStage, Decimal] = {
    "lead": Decimal("0.10"),
    "qualified": Decimal("0.30"),
    "proposal": Decimal("0.55"),
    "negotiation": Decimal("0.75"),
    "won": Decimal("1.00"),
    "lost": Decimal("0.00"),
}


@dataclass(frozen=True, slots=True)
class CommercialOpportunity:
    opportunity_id: str
    account_name: str
    stage: PipelineStage
    value: Decimal
    last_activity_on: date
    expected_close_on: date | None = None
    next_action: str | None = None

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        if not self.account_name.strip():
            raise ValueError("account_name is required")
        if self.stage not in _STAGE_PROBABILITY:
            raise ValueError(f"unsupported pipeline stage: {self.stage}")
        if self.value < 0:
            raise ValueError("opportunity value must not be negative")
        if self.next_action is not None and not self.next_action.strip():
            raise ValueError("next_action must not be blank")

    @property
    def weighted_value(self) -> Decimal:
        return (self.value * _STAGE_PROBABILITY[self.stage]).quantize(Decimal("0.01"))

    def age_days(self, *, as_of: date) -> int:
        return max(0, (as_of - self.last_activity_on).days)

    def is_stalled(self, *, as_of: date, threshold_days: int = 7) -> bool:
        if threshold_days < 1:
            raise ValueError("threshold_days must be positive")
        return self.stage not in {"won", "lost"} and self.age_days(as_of=as_of) >= threshold_days


@dataclass(frozen=True, slots=True)
class CommercialSnapshot:
    pipeline_value: Decimal
    weighted_pipeline_value: Decimal
    open_opportunities: int
    stalled_opportunities: tuple[CommercialOpportunity, ...]
    actions_required: tuple[str, ...]


class CommercialIntelligenceEngine:
    def evaluate(
        self,
        opportunities: Iterable[CommercialOpportunity],
        *,
        as_of: date,
        stalled_after_days: int = 7,
    ) -> CommercialSnapshot:
        items = tuple(opportunities)
        ids = [item.opportunity_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate commercial opportunity_id")

        open_items = tuple(item for item in items if item.stage not in {"won", "lost"})
        stalled = tuple(
            sorted(
                (item for item in open_items if item.is_stalled(as_of=as_of, threshold_days=stalled_after_days)),
                key=lambda item: (-item.age_days(as_of=as_of), -item.weighted_value, item.opportunity_id),
            )
        )
        actions = tuple(
            item.next_action or f"Re-engage {item.account_name}"
            for item in stalled
        )
        return CommercialSnapshot(
            pipeline_value=sum((item.value for item in open_items), Decimal("0.00")),
            weighted_pipeline_value=sum((item.weighted_value for item in open_items), Decimal("0.00")),
            open_opportunities=len(open_items),
            stalled_opportunities=stalled,
            actions_required=actions,
        )
