from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol


InterruptionAction = Literal["send_now", "defer", "suppress"]


@dataclass(frozen=True, slots=True)
class InterruptionContext:
    """Canonical inputs for deciding whether Tony should interrupt a recipient.

    The context is deliberately transport-agnostic. It identifies the workspace
    and recipient, carries the material evidence identities being considered,
    and includes the recorded delivery history needed by the active policy.
    """

    workspace_id: str
    recipient_id: str
    material_ids: tuple[str, ...]
    now: datetime
    last_sent_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.workspace_id.strip():
            raise ValueError("workspace_id is required")
        if not self.recipient_id.strip():
            raise ValueError("recipient_id is required")
        if any(not item.strip() for item in self.material_ids):
            raise ValueError("material_ids must not contain blank values")
        if self.last_sent_at is not None:
            now_is_aware = self.now.tzinfo is not None and self.now.utcoffset() is not None
            last_is_aware = (
                self.last_sent_at.tzinfo is not None
                and self.last_sent_at.utcoffset() is not None
            )
            if now_is_aware != last_is_aware:
                raise ValueError("now and last_sent_at must use compatible timezone awareness")


@dataclass(frozen=True, slots=True)
class InterruptionDecision:
    action: InterruptionAction
    reason: str
    retry_at: datetime | None = None


class InterruptionPolicy(Protocol):
    """Pure decision boundary evaluated before delivery is attempted."""

    def evaluate(self, context: InterruptionContext) -> InterruptionDecision: ...


class FixedCooldownInterruptionPolicy:
    """First deterministic policy: suppress empties and defer within a cooldown.

    This preserves the current proactive escalation rule while moving the
    behavioural decision into a reusable, channel-independent component. It
    performs no I/O and does not mutate delivery history.
    """

    def __init__(self, *, min_interval_seconds: int = 1800) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.min_interval_seconds = min_interval_seconds

    def evaluate(self, context: InterruptionContext) -> InterruptionDecision:
        if not context.material_ids:
            return InterruptionDecision(
                action="suppress",
                reason="no_material",
            )

        if context.last_sent_at is None or self.min_interval_seconds == 0:
            return InterruptionDecision(
                action="send_now",
                reason="material_available",
            )

        retry_at = context.last_sent_at + timedelta(seconds=self.min_interval_seconds)
        if context.now >= retry_at:
            return InterruptionDecision(
                action="send_now",
                reason="cooldown_elapsed",
            )

        return InterruptionDecision(
            action="defer",
            reason="cooldown_active",
            retry_at=retry_at,
        )
