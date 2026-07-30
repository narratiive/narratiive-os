from __future__ import annotations

from typing import Protocol

from runtime.proactive_executive_delivery import EscalationResult
from runtime.recipients import RecipientDirectory


class MaterialEscalationService(Protocol):
    """Existing material-escalation boundary used by recipient-aware composition."""

    def escalate(self, *, workspace_id: str, chat_id: str) -> EscalationResult: ...


class RecipientMaterialEscalationService:
    """Resolve an executive recipient before invoking material escalation.

    The underlying escalation service remains transport-compatible while runtime
    composition can now address a person rather than passing a provider-specific
    Telegram chat identifier through executive logic.
    """

    def __init__(
        self,
        *,
        service: MaterialEscalationService,
        recipients: RecipientDirectory,
        channel: str = "telegram",
    ) -> None:
        canonical_channel = channel.strip().lower()
        if not canonical_channel:
            raise ValueError("channel is required")
        self.service = service
        self.recipients = recipients
        self.channel = canonical_channel

    def escalate(self, *, workspace_id: str, recipient_id: str) -> EscalationResult:
        canonical_workspace_id = workspace_id.strip()
        canonical_recipient_id = recipient_id.strip().lower()
        if not canonical_workspace_id:
            raise ValueError("workspace_id is required")
        if not canonical_recipient_id:
            raise ValueError("recipient_id is required")

        recipient = self.recipients.get(canonical_recipient_id)
        targets = tuple(
            target
            for target in recipient.resolve_targets(
                preferred_channels=(self.channel,),
            )
            if target.channel == self.channel
        )
        if not targets:
            raise LookupError(
                f"recipient {canonical_recipient_id} has no enabled {self.channel} target"
            )
        if len(targets) > 1:
            raise ValueError(
                f"recipient {canonical_recipient_id} has multiple enabled {self.channel} targets"
            )

        return self.service.escalate(
            workspace_id=canonical_workspace_id,
            chat_id=targets[0].address,
        )
