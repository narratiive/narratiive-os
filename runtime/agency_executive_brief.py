from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState


class AgencyBriefPeriod(str, Enum):
    MORNING = "morning"
    EVENING = "evening"


@dataclass(frozen=True, slots=True)
class AgencyExecutiveBrief:
    period: AgencyBriefPeriod
    generated_at: str
    status: str
    commercial: tuple[str, ...]
    clients: tuple[str, ...]
    delivery: tuple[str, ...]
    finance: tuple[str, ...]
    operations: tuple[str, ...]
    automation: tuple[str, ...]
    matt_actions: tuple[str, ...]
    agency_blockers: tuple[str, ...]
    internal_platform_note: str | None
    recommendation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "period": self.period.value,
            "generated_at": self.generated_at,
            "status": self.status,
            "commercial": list(self.commercial),
            "clients": list(self.clients),
            "delivery": list(self.delivery),
            "finance": list(self.finance),
            "operations": list(self.operations),
            "automation": list(self.automation),
            "matt_actions": list(self.matt_actions),
            "agency_blockers": list(self.agency_blockers),
            "internal_platform_note": self.internal_platform_note,
            "recommendation": self.recommendation,
        }

    def render_compact(self, limit: int = 3500) -> str:
        heading = "Morning agency brief" if self.period is AgencyBriefPeriod.MORNING else "End-of-day agency review"
        lines = [f"{heading} — {self.status}"]
        self._append(lines, "Commercial", self.commercial)
        self._append(lines, "Clients", self.clients)
        self._append(lines, "Delivery", self.delivery)
        self._append(lines, "Finance", self.finance)
        self._append(lines, "Operations", self.operations)
        self._append(lines, "Automation", self.automation)
        self._append(lines, "Matt's decisions", self.matt_actions)
        self._append(lines, "Agency blockers", self.agency_blockers)
        if self.internal_platform_note:
            lines.append(f"Internal systems: {self.internal_platform_note}")
        lines.append(f"Tony's recommendation: {self.recommendation}")
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


class AgencyExecutiveBriefService:
    """Render Tony's daily view from agency outcomes, not repository activity."""

    ITEM_LIMIT = 4

    def build(
        self,
        state: AgencyState,
        period: AgencyBriefPeriod = AgencyBriefPeriod.MORNING,
    ) -> AgencyExecutiveBrief:
        visible = state.executive_items
        status = "blocked" if state.agency_blockers else "healthy"
        hidden_count = len(state.hidden_platform_items)
        platform_note = None
        if hidden_count:
            noun = "item is" if hidden_count == 1 else "items are"
            platform_note = f"{hidden_count} engineering or infrastructure {noun} being handled in the background."

        return AgencyExecutiveBrief(
            period=period,
            generated_at=state.generated_at,
            status=status,
            commercial=self._lines(visible, AgencyArea.COMMERCIAL),
            clients=self._lines(visible, AgencyArea.CLIENTS),
            delivery=self._lines(visible, AgencyArea.DELIVERY),
            finance=self._lines(visible, AgencyArea.FINANCE),
            operations=self._lines(visible, AgencyArea.OPERATIONS),
            automation=self._lines(visible, AgencyArea.AUTOMATION),
            matt_actions=tuple(self._line(item) for item in state.matt_actions)[: self.ITEM_LIMIT],
            agency_blockers=tuple(self._line(item) for item in state.agency_blockers)[: self.ITEM_LIMIT],
            internal_platform_note=platform_note,
            recommendation=self._recommendation(state),
        )

    @classmethod
    def _lines(cls, items: tuple[AgencyItem, ...], area: AgencyArea) -> tuple[str, ...]:
        return tuple(cls._line(item) for item in items if item.area is area)[: cls.ITEM_LIMIT]

    @staticmethod
    def _line(item: AgencyItem) -> str:
        return f"{item.title} — {item.next_action}"

    @staticmethod
    def _recommendation(state: AgencyState) -> str:
        business_matt_actions = tuple(
            item for item in state.matt_actions if item.area not in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}
        )
        if business_matt_actions:
            return business_matt_actions[0].next_action
        if state.agency_blockers:
            return state.agency_blockers[0].next_action
        for area in (
            AgencyArea.COMMERCIAL,
            AgencyArea.CLIENTS,
            AgencyArea.DELIVERY,
            AgencyArea.FINANCE,
            AgencyArea.OPERATIONS,
            AgencyArea.AUTOMATION,
        ):
            items = state.items_for(area)
            if items:
                return items[0].next_action
        return "Build the next commercial opportunity while Tony maintains internal systems quietly."
