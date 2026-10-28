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
        status_sentence = (
            "The agency is operational, with no agency-wide blocker."
            if self.status != "blocked"
            else "The agency has a critical outcome-level blocker requiring attention."
        )
        delivery = self._unique(
            self.clients
            + self.delivery
            + self.finance
            + self.operations
            + self.automation
            + self.agency_blockers
        )[:3]
        commercial = self._unique(self.material_changes + self.commercial)[:3] or (
            "Confirmed: no material commercial change since the previous successfully delivered briefing.",
        )
        decisions = self.matt_actions[:3] or ("None confirmed.",)
        priorities = self.recommended_actions[:3] or (self.recommendation,)
        sections = (
            ("2. Commercial opportunities — what changed and why it matters", commercial),
            ("3. Delivery — progress and material blockers", delivery or ("No material change confirmed.",)),
            ("4. Decisions required — explicit founder approvals", decisions),
            ("5. Recommended priorities", priorities),
        )
        lines = [heading, f"1. Agency status — {status_sentence}"]
        for section_heading, values in sections:
            self._append(
                lines,
                section_heading,
                tuple(self._compact(value, 220) for value in values),
            )
        if self.internal_platform_note:
            lines.append(f"Supporting note: {self._compact(self.internal_platform_note, 180)}")
        output = "\n".join(lines)
        if len(output) <= limit:
            return output
        item_budget = max(24, (limit - 310) // len(sections))
        lines = [heading, f"1. Agency status — {self._compact(status_sentence, item_budget)}"]
        for section_heading, values in sections:
            self._append(lines, section_heading, (self._compact(values[0], item_budget),))
        output = "\n".join(lines)
        if len(output) <= limit:
            return output
        return output[: limit - 1].rstrip() + "…"

    @staticmethod
    def _append(lines: list[str], heading: str, values: tuple[str, ...]) -> None:
        lines.append(heading)
        lines.extend(f"- {value}" for value in values)

    @staticmethod
    def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _compact(value: str, limit: int) -> str:
        text = " ".join(value.split())
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"


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
        )[: self.ITEM_LIMIT]
        commercial_items = tuple(
            item for item in visible
            if item.area is AgencyArea.COMMERCIAL
            and item.classification not in {
                "unverified_commercial_contact", "suspicious_commercial_contact",
                "test", "internal", "spam", "duplicate", "deferred", "archived",
            }
        )
        client_items = tuple(
            item for item in visible
            if item.area is AgencyArea.CLIENTS and not item.requires_matt
        )
        delivery_items = tuple(
            item for item in visible
            if item.area is AgencyArea.DELIVERY and not item.requires_matt
        )
        automation_items = tuple(
            item for item in visible
            if item.area is AgencyArea.AUTOMATION and not item.requires_matt
        )
        material_summary = (
            f"{len(visible)} current authoritative item{'s' if len(visible) != 1 else ''} "
            "passed the decision, change and significance checks."
        ) if visible else ()
        return AgencyExecutiveBrief(
            period=period,
            generated_at=state.generated_at,
            status=status,
            commercial=tuple(self._line(item) for item in commercial_items)[: self.ITEM_LIMIT],
            clients=tuple(self._line(item) for item in client_items)[: self.ITEM_LIMIT],
            delivery=tuple(self._line(item) for item in delivery_items)[: self.ITEM_LIMIT],
            finance=tuple(self._line(item) for item in visible if item.area is AgencyArea.FINANCE and not item.requires_matt)[: self.ITEM_LIMIT],
            operations=tuple(self._line(item) for item in visible if item.area is AgencyArea.OPERATIONS and not item.requires_matt)[: self.ITEM_LIMIT],
            automation=tuple(self._line(item) for item in automation_items)[: self.ITEM_LIMIT],
            matt_actions=tuple(self._line(item) for item in state.matt_actions)[: self.ITEM_LIMIT],
            agency_blockers=tuple(
                self._line(item)
                for item in state.agency_blockers
                if item.area in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}
            )[: self.ITEM_LIMIT] or ((
                f"{len(state.agency_blockers)} outcome-level blocker"
                f"{'s' if len(state.agency_blockers) != 1 else ''} require attention."
            ),) if state.agency_blockers else (),
            internal_platform_note=platform_note,
            recommendation=self._recommendation(state),
            material_changes=(material_summary,) if material_summary else (),
            recommended_actions=tuple(
                f"{item.next_action} Owner: {item.owner}. When: {item.action_deadline or 'now or at the next safe operating window'}."
                for item in priority_items
            ),
        )

    @classmethod
    def _lines(cls, items: tuple[AgencyItem, ...], area: AgencyArea) -> tuple[str, ...]:
        return tuple(cls._line(item) for item in items if item.area is area)[: cls.ITEM_LIMIT]

    @staticmethod
    def _line(item: AgencyItem) -> str:
        certainty = "Confirmed" if item.evidence else "Assumption"
        why = item.why_matters or "This materially affects the current agency plan."
        return (
            f"{certainty}: {item.title}. Why it matters: {why} "
            f"Recommended action: {item.next_action}"
        )

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
