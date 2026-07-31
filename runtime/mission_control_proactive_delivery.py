from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

from runtime.executive_trigger import TriggerContext
from runtime.mission_control import MissionControlSnapshot
from runtime.mission_control_change_detection import MissionControlChangeDetector
from runtime.proactive_change_detection import MaterialChange
from runtime.proactive_executive_delivery import EscalationResult


class RecipientEscalationService(Protocol):
    def escalate(self, *, workspace_id: str, recipient_id: str) -> EscalationResult: ...


EventRecorder = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class MissionControlProactiveResult:
    status: str
    workspace_id: str
    recipient_id: str
    changes: tuple[MaterialChange, ...]
    escalation: EscalationResult | None = None

    def __post_init__(self) -> None:
        if self.status not in {"suppressed", "delivered"}:
            raise ValueError(f"unsupported proactive result status: {self.status}")


class MissionControlProactiveDelivery:
    """Deliver one executive escalation only when Mission Control materially changes.

    The durable change detector owns restart-safe suppression. This orchestrator
    preserves trigger evidence, addresses the executive by recipient identity,
    and leaves content rendering, interruption policy and transport delivery to
    the existing escalation boundary.
    """

    def __init__(
        self,
        *,
        detector: MissionControlChangeDetector,
        escalation_service: RecipientEscalationService,
        record_event: EventRecorder | None = None,
    ) -> None:
        self.detector = detector
        self.escalation_service = escalation_service
        self.record_event = record_event

    def run(
        self,
        *,
        context: TriggerContext,
        snapshot: MissionControlSnapshot,
        recipient_id: str,
        now: datetime | None = None,
    ) -> MissionControlProactiveResult:
        if context.source != "mission_control_change":
            raise ValueError("Mission Control proactive delivery requires a mission_control_change trigger")
        canonical_recipient_id = recipient_id.strip().lower()
        if not canonical_recipient_id:
            raise ValueError("recipient_id is required")

        changes = self.detector.detect(
            workspace_id=context.workspace_id,
            snapshot=snapshot,
            now=now or context.fired_at,
        )
        evidence = {
            "workspace_id": context.workspace_id,
            "recipient_id": canonical_recipient_id,
            "change_count": len(changes),
            "changes": [
                {
                    "change_type": change.change_type,
                    "notification_key": change.notification_key,
                    "kind": change.item.kind,
                    "summary": change.item.summary,
                }
                for change in changes
            ],
            **context.evidence(),
        }

        if not changes:
            result = MissionControlProactiveResult(
                status="suppressed",
                workspace_id=context.workspace_id,
                recipient_id=canonical_recipient_id,
                changes=(),
            )
            self._record("mission_control_change.delivery_suppressed", evidence)
            return result

        escalation = self.escalation_service.escalate(
            workspace_id=context.workspace_id,
            recipient_id=canonical_recipient_id,
        )
        result = MissionControlProactiveResult(
            status="delivered",
            workspace_id=context.workspace_id,
            recipient_id=canonical_recipient_id,
            changes=changes,
            escalation=escalation,
        )
        self._record(
            "mission_control_change.delivered",
            {
                **evidence,
                "delivery_status": escalation.status,
                "delivery_attempts": escalation.attempts,
            },
        )
        return result

    def _record(self, event_type: str, evidence: dict[str, Any]) -> None:
        if self.record_event is not None:
            self.record_event({"event_type": event_type, **evidence})
