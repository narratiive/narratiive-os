from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


VALID_DELIVERY_CHANNELS = {"telegram", "email", "slack"}
VALID_EXECUTIVE_MESSAGE_KINDS = {"brief", "escalation"}


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    """A concrete channel destination resolved from an executive recipient."""

    channel: str
    address: str

    def __post_init__(self) -> None:
        channel = self.channel.strip().lower()
        address = self.address.strip()
        if channel not in VALID_DELIVERY_CHANNELS:
            raise ValueError(f"Unsupported delivery channel: {self.channel}")
        if not address:
            raise ValueError("Delivery target address is required")
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "address", address)


@dataclass(frozen=True, slots=True)
class ExecutiveMessageContent:
    """Channel-independent executive content with canonical source evidence."""

    kind: str
    title: str
    summary: str
    data: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        kind = self.kind.strip().lower()
        title = self.title.strip()
        summary = self.summary.strip()
        if kind not in VALID_EXECUTIVE_MESSAGE_KINDS:
            raise ValueError(f"Unsupported executive message kind: {self.kind}")
        if not title:
            raise ValueError("Executive message title is required")
        if not summary:
            raise ValueError("Executive message summary is required")
        evidence = tuple(dict.fromkeys(item.strip() for item in self.evidence if item.strip()))
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "data", dict(self.data))
        object.__setattr__(self, "evidence", evidence)

    @classmethod
    def from_command_response(
        cls,
        *,
        command: str,
        message: str,
        data: Mapping[str, Any],
    ) -> "ExecutiveMessageContent":
        canonical_command = command.strip().lower().lstrip("/")
        evidence_value = data.get("evidence", ())
        evidence = (
            tuple(str(item) for item in evidence_value)
            if isinstance(evidence_value, (list, tuple))
            else ()
        )
        return cls(
            kind="brief",
            title=f"{canonical_command.capitalize()} executive brief",
            summary=message,
            data=data,
            evidence=evidence,
        )

    @classmethod
    def from_materials(cls, materials: list[str]) -> "ExecutiveMessageContent":
        normalised = tuple(sorted({item.strip() for item in materials if item.strip()}))
        if not normalised:
            raise ValueError("Material escalation requires at least one item")
        return cls(
            kind="escalation",
            title="Material escalation",
            summary="Matt review needed.",
            data={"materials": list(normalised)},
            evidence=normalised,
        )


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    """A channel-ready payload without transport-specific side effects."""

    text: str
    subject: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        text = self.text.strip()
        if not text:
            raise ValueError("Rendered message text is required")
        subject = self.subject.strip() if self.subject is not None else None
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "subject", subject or None)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    channel: str
    address: str
    provider_message_id: str | None = None


class ExecutiveMessageRenderer(Protocol):
    def render(self, content: ExecutiveMessageContent) -> RenderedMessage: ...


class ChannelAdapter(Protocol):
    def send(self, target: DeliveryTarget, message: RenderedMessage) -> DeliveryReceipt: ...


class TelegramExecutiveRenderer:
    """Reference renderer preserving the current compact Telegram behaviour."""

    max_characters = 3500

    def render(self, content: ExecutiveMessageContent) -> RenderedMessage:
        if content.kind == "brief":
            text = content.summary
        else:
            materials = tuple(str(item) for item in content.data.get("materials", ()))
            lines = [f"{content.title} — {content.summary}"]
            lines.extend(f"- {item}" for item in materials[:10])
            if len(materials) > 10:
                lines.append(f"...and {len(materials) - 10} more.")
            text = "\n".join(lines)
        return RenderedMessage(
            text=text[: self.max_characters],
            metadata={"kind": content.kind, "evidence": list(content.evidence)},
        )
