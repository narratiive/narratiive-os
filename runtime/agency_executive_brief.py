from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.founder_brief import founder_text


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
    material_changes: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()

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
            "material_changes": list(self.material_changes),
            "recommended_actions": list(self.recommended_actions),
        }

    def render_compact(self, limit: int = 3500) -> str:
        heading = "Morning agency brief" if self.period is AgencyBriefPeriod.MORNING else "End-of-day agency review"
        heading = "Narratiive — Morning Brief" if self.period is AgencyBriefPeriod.MORNING else "Narratiive — Evening Brief"
        lines = [heading]
        self._append(lines, "What matters today", self.material_changes)
        self._append(lines, "Your decisions", self.matt_actions)
        progress = tuple(
            item
            for item in (*self.commercial, *self.clients, *self.delivery)
            if item not in self.material_changes
        )[:3]
        self._append(lines, "Progress", progress)
        self._append(lines, "Risks", self.agency_blockers)
        self._append(lines, "Tony's next actions", self.recommended_actions)
        if len(lines) == 1:
            lines.append("No material change since the last briefing. I’m handling routine operations quietly.")
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

    ITEM_LIMIT = 3

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

        priority = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
        priority_items = tuple(
            sorted(
                visible,
                key=lambda item: (
                    priority.get(item.significance, 4),
                    0 if item.requires_matt else 1,
                    0 if item.blocked else 1,
                    item.title.casefold(),
                ),
            )
        )
        business_items = tuple(
            item
            for item in priority_items
            if (
                item.area not in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}
                and item.significance != "P4"
            )
        )
        commercial_items = tuple(
            item for item in visible
            if item.area is AgencyArea.COMMERCIAL and not item.requires_matt and not item.blocked and item.significance != "P4"
            and item.classification not in {
                "unverified_commercial_contact", "suspicious_commercial_contact",
                "test", "internal", "spam", "duplicate", "deferred", "archived",
            }
        )
        client_items = tuple(
            item for item in visible
            if item.area is AgencyArea.CLIENTS and not item.requires_matt and not item.blocked and item.significance != "P4"
        )
        delivery_items = tuple(
            item for item in visible
            if item.area is AgencyArea.DELIVERY and not item.requires_matt and not item.blocked and item.significance != "P4"
        )
        automation_items = tuple(
            item for item in visible
            if item.area is AgencyArea.AUTOMATION and not item.requires_matt
        )
        material_summary = tuple(
            self._summary(item)
            for item in business_items
            if not item.requires_matt and not item.blocked
        )[:2]
        return AgencyExecutiveBrief(
            period=period,
            generated_at=state.generated_at,
            status=status,
            commercial=tuple(self._summary(item) for item in commercial_items)[: self.ITEM_LIMIT],
            clients=tuple(self._summary(item) for item in client_items)[: self.ITEM_LIMIT],
            delivery=tuple(self._summary(item) for item in delivery_items)[: self.ITEM_LIMIT],
            finance=tuple(self._summary(item) for item in visible if item.area is AgencyArea.FINANCE and not item.requires_matt)[: self.ITEM_LIMIT],
            operations=tuple(self._summary(item) for item in visible if item.area is AgencyArea.OPERATIONS and not item.requires_matt)[: self.ITEM_LIMIT],
            automation=tuple(self._summary(item) for item in automation_items)[: self.ITEM_LIMIT],
            matt_actions=tuple(self._decision(item) for item in state.matt_actions)[: self.ITEM_LIMIT],
            agency_blockers=tuple(
                self._risk(item) for item in state.agency_blockers
            )[: self.ITEM_LIMIT],
            internal_platform_note=platform_note,
            recommendation=self._recommendation(state),
            material_changes=material_summary,
            recommended_actions=tuple(
                founder_text(item.next_action, limit=220)
                for item in business_items
                if not item.requires_matt and item.next_action.strip()
            )[: self.ITEM_LIMIT],
        )

    @classmethod
    def _lines(cls, items: tuple[AgencyItem, ...], area: AgencyArea) -> tuple[str, ...]:
        return tuple(cls._line(item) for item in items if item.area is area)[: cls.ITEM_LIMIT]

    @staticmethod
    def _summary(item: AgencyItem) -> str:
        why = founder_text(item.why_matters, limit=150)
        title = founder_text(item.title, limit=110)
        return f"{title} — {why}" if why else title

    @staticmethod
    def _decision(item: AgencyItem) -> str:
        title = founder_text(item.title, limit=100)
        action = founder_text(item.next_action, limit=180)
        deadline = founder_text(item.action_deadline, limit=60)
        suffix = f" By {deadline}." if deadline else ""
        return f"{title}: {action}{suffix}"

    @staticmethod
    def _risk(item: AgencyItem) -> str:
        title = founder_text(item.title, limit=100)
        consequence = founder_text(item.why_matters, limit=160)
        return f"{title} — {consequence}" if consequence else title

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
