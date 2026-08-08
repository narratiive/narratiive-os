from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Literal

PriorityKind = Literal["commercial", "operational"]


@dataclass(frozen=True, slots=True)
class ExecutivePriorityCandidate:
    candidate_id: str
    title: str
    kind: PriorityKind
    urgency: int
    strategic_value: int
    commercial_value: Decimal = Decimal("0.00")
    blocked: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.title.strip():
            raise ValueError("title is required")
        if self.kind not in {"commercial", "operational"}:
            raise ValueError(f"unsupported priority kind: {self.kind}")
        for name, value in (("urgency", self.urgency), ("strategic_value", self.strategic_value)):
            if value < 0 or value > 5:
                raise ValueError(f"{name} must be between 0 and 5")
        if self.commercial_value < 0:
            raise ValueError("commercial_value must not be negative")


@dataclass(frozen=True, slots=True)
class RankedExecutivePriority:
    rank: int
    candidate_id: str
    title: str
    kind: PriorityKind
    score: Decimal
    reason: str


class ExecutivePriorityRanker:
    """Rank commercial and operational work into a short executive agenda."""

    def rank(
        self,
        candidates: Iterable[ExecutivePriorityCandidate],
        *,
        limit: int = 3,
    ) -> tuple[RankedExecutivePriority, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        items = tuple(candidates)
        ids = [item.candidate_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate executive priority candidate_id")

        scored = sorted(
            ((self._score(item), item) for item in items),
            key=lambda pair: (-pair[0], pair[1].candidate_id),
        )[:limit]

        return tuple(
            RankedExecutivePriority(
                rank=index,
                candidate_id=item.candidate_id,
                title=item.title,
                kind=item.kind,
                score=score.quantize(Decimal("0.01")),
                reason=self._reason(item),
            )
            for index, (score, item) in enumerate(scored, start=1)
        )

    @staticmethod
    def _score(item: ExecutivePriorityCandidate) -> Decimal:
        score = Decimal(item.urgency * 4 + item.strategic_value * 3)
        if item.kind == "commercial":
            score += Decimal("6")
            score += min(item.commercial_value / Decimal("1000"), Decimal("10"))
        if item.blocked:
            score += Decimal("3")
        return score

    @staticmethod
    def _reason(item: ExecutivePriorityCandidate) -> str:
        reasons: list[str] = []
        if item.kind == "commercial":
            reasons.append("commercial impact")
        if item.urgency >= 4:
            reasons.append("time-sensitive")
        if item.strategic_value >= 4:
            reasons.append("strategically important")
        if item.blocked:
            reasons.append("currently blocked")
        return ", ".join(reasons) if reasons else "important executive work"
