from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Protocol

from runtime.proactive_executive_delivery import EscalationResult, ProactiveDeliveryResult


TriggerSource = Literal["scheduled", "manual", "mission_control_change"]


@dataclass(frozen=True, slots=True)
class TriggerContext:
    """Transport-neutral evidence describing why an executive delivery ran.

    Every entry point creates this value before invoking delivery logic. The
    correlation identifier is preserved verbatim so scheduler, webhook and
    Mission Control evidence can be joined without teaching delivery services
    about the trigger that called them.
    """

    source: TriggerSource
    correlation_id: str
    workspace_id: str
    fired_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        correlation_id = self.correlation_id.strip()
        workspace_id = self.workspace_id.strip()
        if not correlation_id:
            raise ValueError("correlation_id is required")
        if not workspace_id:
            raise ValueError("workspace_id is required")
        if self.fired_at.tzinfo is None or self.fired_at.utcoffset() is None:
            raise ValueError("fired_at must be timezone-aware")

        canonical_metadata: dict[str, str] = {}
        for raw_key, raw_value in self.metadata.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not key or not value:
                raise ValueError("trigger metadata keys and values must not be blank")
            canonical_metadata[key] = value

        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "workspace_id", workspace_id)
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(sorted(canonical_metadata.items()))),
        )

    def evidence(self) -> dict[str, Any]:
        return {
            "trigger_source": self.source,
            "correlation_id": self.correlation_id,
            "triggered_at": self.fired_at.isoformat(),
            "trigger_metadata": dict(self.metadata),
        }


class EscalationService(Protocol):
    def escalate(self, *, workspace_id: str, chat_id: str) -> EscalationResult: ...


class BriefDeliveryService(Protocol):
    def deliver(
        self,
        *,
        workspace_id: str,
        chat_id: str,
        command: str,
        delivery_date: Any = None,
    ) -> ProactiveDeliveryResult: ...


EventRecorder = Callable[[dict[str, Any]], None]


def run_triggered_escalation(
    *,
    service: EscalationService,
    context: TriggerContext,
    recipient_address: str,
    record_event: EventRecorder | None = None,
) -> EscalationResult:
    """Run one escalation from any trigger entry point with shared evidence."""

    address = recipient_address.strip()
    if not address:
        raise ValueError("recipient_address is required")

    if record_event is not None:
        record_event(
            {
                "event_type": "executive_trigger.received",
                "delivery_kind": "escalation",
                "workspace_id": context.workspace_id,
                **context.evidence(),
            }
        )

    return service.escalate(
        workspace_id=context.workspace_id,
        chat_id=address,
    )


def run_triggered_brief(
    *,
    service: BriefDeliveryService,
    context: TriggerContext,
    recipient_address: str,
    command: str,
    record_event: EventRecorder | None = None,
) -> ProactiveDeliveryResult:
    """Run one scheduled or manual brief through the same trigger boundary."""

    address = recipient_address.strip()
    canonical_command = command.strip().lower().lstrip("/")
    if not address:
        raise ValueError("recipient_address is required")
    if canonical_command not in {"morning", "evening"}:
        raise ValueError(f"Unsupported proactive command: {command}")

    if record_event is not None:
        record_event(
            {
                "event_type": "executive_trigger.received",
                "delivery_kind": "brief",
                "command": canonical_command,
                "workspace_id": context.workspace_id,
                **context.evidence(),
            }
        )

    return service.deliver(
        workspace_id=context.workspace_id,
        chat_id=address,
        command=canonical_command,
        delivery_date=context.fired_at.date(),
    )
