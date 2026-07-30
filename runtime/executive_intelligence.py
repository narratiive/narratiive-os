from __future__ import annotations

from dataclasses import dataclass

from runtime.agency_state import AREA_PRIORITY, AgencyArea, AgencyItem, AgencyState


@dataclass(frozen=True, slots=True)
class ExecutiveDirection:
    focus: tuple[AgencyItem, ...]
    tony_handles: tuple[AgencyItem, ...]
    matt_decisions: tuple[AgencyItem, ...]
    interruptions: tuple[AgencyItem, ...]
    recommendation: str


class ExecutiveIntelligenceService:
    """Translate agency state into clear executive direction for Matt and Tony."""

    FOCUS_LIMIT = 3
    HANDLE_LIMIT = 4

    def analyse(self, state: AgencyState) -> ExecutiveDirection:
        business_items = tuple(
            item
            for item in state.executive_items
            if item.area not in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}
        )
        matt_decisions = tuple(item for item in business_items if item.requires_matt)
        interruptions = tuple(
            item
            for item in state.executive_items
            if item.requires_matt and (item.blocked or item.blocks_agency_outcome)
        )
        focus = tuple(sorted(business_items, key=self._focus_key))[: self.FOCUS_LIMIT]
        tony_handles = tuple(
            item
            for item in state.executive_items
            if not item.requires_matt
        )[: self.HANDLE_LIMIT]

        return ExecutiveDirection(
            focus=focus,
            tony_handles=tony_handles,
            matt_decisions=matt_decisions,
            interruptions=interruptions,
            recommendation=self._recommendation(focus, matt_decisions, state),
        )

    @staticmethod
    def _focus_key(item: AgencyItem) -> tuple[int, int, int, str]:
        return (
            0 if item.requires_matt else 1,
            0 if item.blocked else 1,
            AREA_PRIORITY[item.area],
            item.title.casefold(),
        )

    @staticmethod
    def _recommendation(
        focus: tuple[AgencyItem, ...],
        matt_decisions: tuple[AgencyItem, ...],
        state: AgencyState,
    ) -> str:
        if matt_decisions:
            return matt_decisions[0].next_action
        if focus:
            return focus[0].next_action
        if state.agency_blockers:
            return state.agency_blockers[0].next_action
        return "Create the next qualified commercial opportunity while Tony handles internal operations quietly."
