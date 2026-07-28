from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ExecutiveMessageContent:
    """Channel-neutral executive content produced by Tony runtime services."""

    kind: str
    title: str
    items: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        kind = self.kind.strip()
        title = self.title.strip()
        items = tuple(dict.fromkeys(item.strip() for item in self.items if item.strip()))
        if not kind:
            raise ValueError("kind is required")
        if not title:
            raise ValueError("title is required")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    """Concrete channel destination resolved at dispatch time."""

    channel: str
    address: str

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
class RenderedMessage:
    """Channel-shaped message ready for a delivery adapter."""

    text: str
    subject: str | None = None
    html: str | None = None

    def __post_init__(self) -> None:
        text = self.text.strip()
        if not text:
            raise ValueError("text is required")
        object.__setattr__(self, "text", text)
        if self.subject is not None:
            object.__setattr__(self, "subject", self.subject.strip() or None)
        if self.html is not None:
            object.__setattr__(self, "html", self.html.strip() or None)


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """Canonical evidence that a channel adapter accepted a delivery."""

    channel: str
    address: str
    provider_message_id: str | None = None

    def __post_init__(self) -> None:
        channel = self.channel.strip().lower()
        address = self.address.strip()
        provider_message_id = (
            self.provider_message_id.strip() if self.provider_message_id is not None else None
        )
        if not channel:
            raise ValueError("channel is required")
        if not address:
            raise ValueError("address is required")
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "address", address)
        object.__setattr__(self, "provider_message_id", provider_message_id or None)


class ExecutiveMessageRenderer(Protocol):
    def render(self, content: ExecutiveMessageContent) -> RenderedMessage: ...


class ChannelAdapter(Protocol):
    def send(self, target: DeliveryTarget, message: RenderedMessage) -> DeliveryReceipt: ...


class TelegramTextRenderer:
    """Render structured executive content within Telegram's safe text envelope."""

    def __init__(self, *, max_items: int = 10, max_characters: int = 3500) -> None:
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        if max_characters < 1:
            raise ValueError("max_characters must be at least 1")
        self.max_items = max_items
        self.max_characters = max_characters

    def render(self, content: ExecutiveMessageContent) -> RenderedMessage:
        lines = [content.title]
        lines.extend(f"- {item}" for item in content.items[: self.max_items])
        if len(content.items) > self.max_items:
            lines.append(f"...and {len(content.items) - self.max_items} more.")
        return RenderedMessage(text="\n".join(lines)[: self.max_characters])


class CallableTextChannelAdapter:
    """Compatibility adapter for existing two-string sender callables."""

    def __init__(self, *, channel: str, send_text) -> None:
        canonical_channel = channel.strip().lower()
        if not canonical_channel:
            raise ValueError("channel is required")
        if not callable(send_text):
            raise TypeError("send_text must be callable")
        self.channel = canonical_channel
        self.send_text = send_text

    def send(self, target: DeliveryTarget, message: RenderedMessage) -> DeliveryReceipt:
        if target.channel != self.channel:
            raise ValueError(
                f"target channel {target.channel!r} is not supported by {self.channel!r} adapter"
            )
        self.send_text(target.address, message.text)
        return DeliveryReceipt(channel=target.channel, address=target.address)
