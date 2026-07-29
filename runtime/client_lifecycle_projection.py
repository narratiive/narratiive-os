from __future__ import annotations

from collections.abc import Iterable

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage


class ClientLifecycleProjector:
    """Project client lifecycle evidence into Tony's canonical AgencyState."""

    def enrich(
        self,
        state: AgencyState,
        records: Iterable[ClientLifecycleRecord],
    ) -> AgencyState:
        lifecycle_items = tuple(self._item(record) for record in records)
        retained = tuple(item for item in state.items if item.item_id != "commercial-empty-state")
        return AgencyState.from_items(state.generated_at, (*retained, *lifecycle_items))

    @staticmethod
    def _item(record: ClientLifecycleRecord) -> AgencyItem:
        area = ClientLifecycleProjector._area(record.stage)
        value = f" · £{record.value_gbp:,}" if record.value_gbp is not None else ""
        title = f"{record.client_name} — {record.stage.value.replace('_', ' ').title()}{value}"
        evidence = record.evidence or (f"client_lifecycle:{record.client_id}:{record.stage.value}",)
        return AgencyItem(
            item_id=f"client-{record.client_id}",
            area=area,
            title=title,
            status="blocked" if record.blocked else record.stage.value,
            next_action=record.next_action,
            owner=record.owner,
            evidence=evidence,
            blocked=record.blocked,
            blocks_agency_outcome=record.blocked,
            requires_matt=record.requires_matt,
        )

    @staticmethod
    def _area(stage: ClientLifecycleStage) -> AgencyArea:
        if stage is ClientLifecycleStage.DELIVERY:
            return AgencyArea.DELIVERY
        if stage in {ClientLifecycleStage.INVOICE, ClientLifecycleStage.COMPLETE}:
            return AgencyArea.FINANCE
        return AgencyArea.COMMERCIAL
