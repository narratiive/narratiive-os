from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ClientLifecycleStage(str, Enum):
    LEAD = "lead"
    RESEARCH = "research"
    BLUEPRINT_LITE = "blueprint_lite"
    OUTREACH = "outreach"
    MEETING = "meeting"
    PROPOSAL = "proposal"
    DELIVERY = "delivery"
    INVOICE = "invoice"
    COMPLETE = "complete"

    @classmethod
    def _missing_(cls, value: object) -> "ClientLifecycleStage | None":
        # Backwards compatibility for lifecycle records created before
        # Blueprint Lite became the canonical inbound product name.
        if value == "narrative_shift":
            return cls.BLUEPRINT_LITE
        return None


_STAGE_ORDER = tuple(ClientLifecycleStage)


class AcquisitionPath(str, Enum):
    """Explicit acquisition journey without rewriting legacy lifecycle history."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    LEGACY = "legacy"


_PATH_STAGE_ORDER = {
    AcquisitionPath.INBOUND: (
        ClientLifecycleStage.LEAD,
        ClientLifecycleStage.BLUEPRINT_LITE,
        ClientLifecycleStage.MEETING,
        ClientLifecycleStage.PROPOSAL,
        ClientLifecycleStage.DELIVERY,
        ClientLifecycleStage.INVOICE,
        ClientLifecycleStage.COMPLETE,
    ),
    AcquisitionPath.OUTBOUND: (
        ClientLifecycleStage.LEAD,
        ClientLifecycleStage.RESEARCH,
        ClientLifecycleStage.OUTREACH,
        ClientLifecycleStage.MEETING,
        ClientLifecycleStage.PROPOSAL,
        ClientLifecycleStage.DELIVERY,
        ClientLifecycleStage.INVOICE,
        ClientLifecycleStage.COMPLETE,
    ),
    AcquisitionPath.LEGACY: _STAGE_ORDER,
}


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
    acquisition_path: AcquisitionPath = AcquisitionPath.LEGACY

    def __post_init__(self) -> None:
        if not isinstance(self.stage, ClientLifecycleStage):
            raise ValueError("stage must be a ClientLifecycleStage")
        if not isinstance(self.acquisition_path, AcquisitionPath):
            raise ValueError("acquisition_path must be an AcquisitionPath")
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
        if self.stage not in _PATH_STAGE_ORDER[self.acquisition_path]:
            raise ValueError(
                f"stage {self.stage.value} is not valid for {self.acquisition_path.value} acquisition"
            )

    @property
    def stage_index(self) -> int:
        return _PATH_STAGE_ORDER[self.acquisition_path].index(self.stage)

    @property
    def is_commercial(self) -> bool:
        return self.stage in {
            ClientLifecycleStage.LEAD,
            ClientLifecycleStage.RESEARCH,
            ClientLifecycleStage.BLUEPRINT_LITE,
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
        stage_order = _PATH_STAGE_ORDER[self.acquisition_path]
        expected_index = self.stage_index + 1
        if expected_index >= len(stage_order) or stage_order[expected_index] is not next_stage:
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
            acquisition_path=self.acquisition_path,
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
            "acquisition_path": self.acquisition_path.value,
        }
