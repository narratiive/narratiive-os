from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Iterable


class AgencyArea(str, Enum):
    COMMERCIAL = "commercial"
    CLIENTS = "clients"
    DELIVERY = "delivery"
    FINANCE = "finance"
    OPERATIONS = "operations"
    AUTOMATION = "automation"
    ENGINEERING = "engineering"
    INFRASTRUCTURE = "infrastructure"


AREA_PRIORITY: dict[AgencyArea, int] = {
    AgencyArea.COMMERCIAL: 0,
    AgencyArea.CLIENTS: 1,
    AgencyArea.DELIVERY: 2,
    AgencyArea.FINANCE: 3,
    AgencyArea.OPERATIONS: 4,
    AgencyArea.AUTOMATION: 5,
    AgencyArea.ENGINEERING: 6,
    AgencyArea.INFRASTRUCTURE: 7,
}


@dataclass(frozen=True, slots=True)
class AgencyItem:
    item_id: str
    area: AgencyArea
    title: str
    status: str
    next_action: str
    owner: str = "Tony"
    evidence: tuple[str, ...] = ()
    blocked: bool = False
    blocks_agency_outcome: bool = False
    requires_matt: bool = False

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("Agency items require an item_id")
        if not self.title.strip():
            raise ValueError("Agency items require a title")
        if not self.status.strip():
            raise ValueError("Agency items require a status")
        if not self.next_action.strip():
            raise ValueError("Agency items require a next action")

    @property
    def executive_visible(self) -> bool:
        if self.area in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}:
            return self.blocks_agency_outcome or self.requires_matt
        return True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["area"] = self.area.value
        return payload


@dataclass(frozen=True, slots=True)
class AgencyState:
    generated_at: str
    items: tuple[AgencyItem, ...] = ()

    @classmethod
    def from_items(cls, generated_at: str, items: Iterable[AgencyItem]) -> "AgencyState":
        return cls(generated_at=generated_at, items=tuple(items))

    @property
    def executive_items(self) -> tuple[AgencyItem, ...]:
        return tuple(
            sorted(
                (item for item in self.items if item.executive_visible),
                key=lambda item: (
                    AREA_PRIORITY[item.area],
                    0 if item.blocked else 1,
                    item.title.casefold(),
                ),
            )
        )

    @property
    def hidden_platform_items(self) -> tuple[AgencyItem, ...]:
        return tuple(item for item in self.items if not item.executive_visible)

    @property
    def matt_actions(self) -> tuple[AgencyItem, ...]:
        return tuple(item for item in self.executive_items if item.requires_matt)

    @property
    def agency_blockers(self) -> tuple[AgencyItem, ...]:
        return tuple(item for item in self.executive_items if item.blocked)

    def items_for(self, area: AgencyArea) -> tuple[AgencyItem, ...]:
        return tuple(item for item in self.executive_items if item.area is area)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "items": [item.to_dict() for item in self.items],
            "executive_items": [item.to_dict() for item in self.executive_items],
            "hidden_platform_items": [item.to_dict() for item in self.hidden_platform_items],
        }
