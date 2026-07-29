from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ClientLifecycleStage(str, Enum):
    LEAD = "lead"
    RESEARCH = "research"
    NARRATIVE_SHIFT = "narrative_shift"
    OUTREACH = "outreach"
    MEETING = "meeting"
    PROPOSAL = "proposal"
    DELIVERY = "delivery"
    INVOICE = "invoice"
    COMPLETE = "complete"


_STAGE_ORDER = tuple(ClientLifecycleStage)


@dataclass(frozen=True, slots=True)
class ClientLifecycleRecord:
    client_id: str
    client_name: str
    stage: ClientLifecycleStage
    owner: str
    next_action: str
    evidence: tuple[str, ...] = ()
    blocked: bool = False
    blocker: str | None = None
    requires_matt: bool = False
    value_gbp: int | None = None

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise ValueError("client_id is required")
        if not self.client_name.strip():
            raise ValueError("client_name is required")
        if not self.owner.strip():
            raise ValueError("owner is required")
        if not self.next_action.strip():
            raise ValueError("next_action is required")
        if self.blocked and not (self.blocker and self.blocker.strip()):
            raise ValueError("blocked lifecycle records require a blocker")
        if self.value_gbp is not None and self.value_gbp < 0:
            raise ValueError("value_gbp cannot be negative")

    @property
    def stage_index(self) -> int:
        return _STAGE_ORDER.index(self.stage)

    @property
    def is_commercial(self) -> bool:
        return self.stage in {
            ClientLifecycleStage.LEAD,
            ClientLifecycleStage.RESEARCH,
            ClientLifecycleStage.NARRATIVE_SHIFT,
            ClientLifecycleStage.OUTREACH,
            ClientLifecycleStage.MEETING,
            ClientLifecycleStage.PROPOSAL,
        }

    @property
    def is_delivery(self) -> bool:
        return self.stage is ClientLifecycleStage.DELIVERY

    @property
    def is_finance(self) -> bool:
        return self.stage in {ClientLifecycleStage.INVOICE, ClientLifecycleStage.COMPLETE}

    def advance(self, next_stage: ClientLifecycleStage, *, next_action: str) -> "ClientLifecycleRecord":
        expected_index = self.stage_index + 1
        if expected_index >= len(_STAGE_ORDER) or _STAGE_ORDER[expected_index] is not next_stage:
            raise ValueError(
                f"invalid lifecycle transition: {self.stage.value} -> {next_stage.value}"
            )
        return ClientLifecycleRecord(
            client_id=self.client_id,
            client_name=self.client_name,
            stage=next_stage,
            owner=self.owner,
            next_action=next_action,
            evidence=self.evidence,
            blocked=False,
            blocker=None,
            requires_matt=False,
            value_gbp=self.value_gbp,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "client_name": self.client_name,
            "stage": self.stage.value,
            "owner": self.owner,
            "next_action": self.next_action,
            "evidence": list(self.evidence),
            "blocked": self.blocked,
            "blocker": self.blocker,
            "requires_matt": self.requires_matt,
            "value_gbp": self.value_gbp,
        }
