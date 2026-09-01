from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage


class AutonomyAction(str, Enum):
    CONTINUE = "continue_autonomously"
    APPROVAL = "await_human_approval"
    ESCALATE = "escalate_blocker"


_HUMAN_GATE_STAGES = {
    ClientLifecycleStage.OUTREACH,
    ClientLifecycleStage.MEETING,
    ClientLifecycleStage.PROPOSAL,
    ClientLifecycleStage.DELIVERY,
    ClientLifecycleStage.INVOICE,
}


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    client_id: str
    client_name: str
    stage: ClientLifecycleStage
    action: AutonomyAction
    next_action: str
    reason: str
    requires_human: bool
    evidence: tuple[str, ...]
    value_gbp: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "client_name": self.client_name,
            "stage": self.stage.value,
            "action": self.action.value,
            "next_action": self.next_action,
            "reason": self.reason,
            "requires_human": self.requires_human,
            "evidence": list(self.evidence),
            "value_gbp": self.value_gbp,
        }


@dataclass(frozen=True, slots=True)
class AutonomyPlan:
    autonomous_queue: tuple[AutonomyDecision, ...]
    human_queue: tuple[AutonomyDecision, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "autonomous_queue": [item.to_dict() for item in self.autonomous_queue],
            "human_queue": [item.to_dict() for item in self.human_queue],
        }


class TonyAutonomyPlanner:
    """Classify lifecycle work using the repository's existing authority boundaries.

    This service has no side effects. It tells orchestration code what may progress
    internally and what must stop for a blocker or authorised-human decision.
    """

    def decide(self, record: ClientLifecycleRecord) -> AutonomyDecision:
        if record.blocked:
            return self._decision(
                record,
                AutonomyAction.ESCALATE,
                reason=record.blocker or "Lifecycle work is blocked.",
                requires_human=True,
            )

        if record.requires_matt:
            return self._decision(
                record,
                AutonomyAction.APPROVAL,
                reason="The lifecycle record explicitly requires Matt's decision.",
                requires_human=True,
            )

        if record.stage in _HUMAN_GATE_STAGES:
            return self._decision(
                record,
                AutonomyAction.APPROVAL,
                reason=(
                    "This stage can create a client-facing, scheduling, commercial, "
                    "delivery, or financial consequence and therefore requires the "
                    "existing authorised-human gate before execution."
                ),
                requires_human=True,
            )

        return self._decision(
            record,
            AutonomyAction.CONTINUE,
            reason=(
                "This is internal preparation or bookkeeping inside the approved "
                "workflow and may progress autonomously while evidence and other "
                "workflow gates remain satisfied."
            ),
            requires_human=False,
        )

    def plan(self, records: Iterable[ClientLifecycleRecord]) -> AutonomyPlan:
        decisions = tuple(self.decide(record) for record in records)
        autonomous = tuple(
            sorted(
                (item for item in decisions if not item.requires_human),
                key=self._priority_key,
            )
        )
        human = tuple(
            sorted(
                (item for item in decisions if item.requires_human),
                key=self._human_priority_key,
            )
        )
        return AutonomyPlan(autonomous_queue=autonomous, human_queue=human)

    @staticmethod
    def _decision(
        record: ClientLifecycleRecord,
        action: AutonomyAction,
        *,
        reason: str,
        requires_human: bool,
    ) -> AutonomyDecision:
        return AutonomyDecision(
            client_id=record.client_id,
            client_name=record.client_name,
            stage=record.stage,
            action=action,
            next_action=record.next_action,
            reason=reason,
            requires_human=requires_human,
            evidence=record.evidence,
            value_gbp=record.value_gbp,
        )

    @staticmethod
    def _priority_key(item: AutonomyDecision) -> tuple[int, int, str]:
        # Progress the furthest-advanced internal work first; value is a secondary
        # commercial signal only and never overrides an approval boundary.
        return (-list(ClientLifecycleStage).index(item.stage), -(item.value_gbp or 0), item.client_id)

    @staticmethod
    def _human_priority_key(item: AutonomyDecision) -> tuple[int, int, str]:
        # Blockers precede ordinary approvals; within each class surface higher
        # known commercial value first, then use stable identity for determinism.
        blocker_rank = 0 if item.action is AutonomyAction.ESCALATE else 1
        return (blocker_rank, -(item.value_gbp or 0), item.client_id)
