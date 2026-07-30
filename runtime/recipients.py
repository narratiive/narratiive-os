from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from runtime.executive_delivery import DeliveryTarget


@dataclass(frozen=True, slots=True)
class RecipientAddress:
    """One channel address belonging to an executive recipient."""

    channel: str
    address: str
    enabled: bool = True

    def __post_init__(self) -> None:
        channel = self.channel.strip().lower()
        address = self.address.strip()
        if not channel:
            raise ValueError("channel is required")
        if not address:
            raise ValueError("address is required")
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "address", address)


@dataclass(frozen=True, slots=True)
class Recipient:
    """A person Tony can notify, independent of any delivery provider."""

    recipient_id: str
    display_name: str
    addresses: tuple[RecipientAddress, ...]

    def __post_init__(self) -> None:
        recipient_id = self.recipient_id.strip().lower()
        display_name = self.display_name.strip()
        if not recipient_id:
            raise ValueError("recipient_id is required")
        if not display_name:
            raise ValueError("display_name is required")

        canonical: dict[tuple[str, str], RecipientAddress] = {}
        for item in self.addresses:
            key = (item.channel, item.address)
            canonical[key] = item

        object.__setattr__(self, "recipient_id", recipient_id)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(
            self,
            "addresses",
            tuple(canonical[key] for key in sorted(canonical)),
        )

    def resolve_targets(
        self,
        *,
        preferred_channels: Iterable[str] = (),
    ) -> tuple[DeliveryTarget, ...]:
        """Resolve enabled addresses deterministically, honouring channel preference."""

        preferred = tuple(
            dict.fromkeys(channel.strip().lower() for channel in preferred_channels if channel.strip())
        )
        rank = {channel: index for index, channel in enumerate(preferred)}
        enabled = [item for item in self.addresses if item.enabled]
        enabled.sort(
            key=lambda item: (
                rank.get(item.channel, len(rank)),
                item.channel,
                item.address,
            )
        )
        return tuple(
            DeliveryTarget(channel=item.channel, address=item.address)
            for item in enabled
        )


class RecipientDirectory:
    """Deterministic in-memory directory used by runtime composition boundaries."""

    def __init__(self, recipients: Iterable[Recipient]) -> None:
        by_id: dict[str, Recipient] = {}
        for recipient in recipients:
            if recipient.recipient_id in by_id:
                raise ValueError(f"duplicate recipient_id: {recipient.recipient_id}")
            by_id[recipient.recipient_id] = recipient
        self._recipients = by_id

    def get(self, recipient_id: str) -> Recipient:
        canonical_id = recipient_id.strip().lower()
        if not canonical_id:
            raise ValueError("recipient_id is required")
        try:
            return self._recipients[canonical_id]
        except KeyError as exc:
            raise KeyError(f"unknown recipient_id: {canonical_id}") from exc
