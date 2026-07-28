from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Callable, Iterable

from runtime.executive_delivery import (
    CallableTextChannelAdapter,
    ChannelAdapter,
    DeliveryTarget,
    ExecutiveMessageContent,
    ExecutiveMessageRenderer,
    TelegramTextRenderer,
)
from runtime.interruption_policy import InterruptionContext, InterruptionPolicy
from runtime.mission_control import MissionControlSnapshot
from runtime.proactive_executive_delivery import (
    DeliveryKeyStore,
    EscalationResult,
    FileLastEscalationStore,
    IdempotentDispatcher,
)


MessageSender = Callable[[str, str], None]
EventRecorder = Callable[[dict[str, Any]], None]
Clock = Callable[[], datetime]
MissionControlLoader = Callable[[], MissionControlSnapshot]


class PolicyGovernedMaterialEscalationService:
    """Escalate Mission Control material only when interruption policy permits it.

    Duplicate suppression remains ahead of interruption-policy evaluation. The
    service now passes channel-neutral content to a renderer and channel adapter,
    while the legacy two-string sender remains supported for current composition.
    Successful delivery remains the only operation that advances delivery history.
    """

    def __init__(
        self,
        *,
        mission_control_loader: MissionControlLoader,
        key_store: DeliveryKeyStore,
        last_sent_store: FileLastEscalationStore,
        interruption_policy: InterruptionPolicy,
        record_event: EventRecorder,
        send_message: MessageSender | None = None,
        channel_adapter: ChannelAdapter | None = None,
        renderer: ExecutiveMessageRenderer | None = None,
        channel: str = "telegram",
        clock: Clock | None = None,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if send_message is None and channel_adapter is None:
            raise ValueError("send_message or channel_adapter is required")
        if send_message is not None and channel_adapter is not None:
            raise ValueError("provide send_message or channel_adapter, not both")
        canonical_channel = channel.strip().lower()
        if not canonical_channel:
            raise ValueError("channel is required")
        self.mission_control_loader = mission_control_loader
        self.channel = canonical_channel
        self.channel_adapter = channel_adapter or CallableTextChannelAdapter(
            channel=canonical_channel,
            send_text=send_message,
        )
        self.renderer = renderer or TelegramTextRenderer()
        self.last_sent_store = last_sent_store
        self.interruption_policy = interruption_policy
        self.record_event = record_event
        self.clock = clock or datetime.now
        self.max_attempts = max_attempts
        self.dispatcher = IdempotentDispatcher(key_store=key_store)

    def escalate(self, *, workspace_id: str, chat_id: str) -> EscalationResult:
        canonical_workspace_id = workspace_id.strip()
        canonical_chat_id = chat_id.strip()
        if not canonical_workspace_id:
            raise ValueError("workspace_id is required")
        if not canonical_chat_id:
            raise ValueError("chat_id is required")

        try:
            snapshot = self.mission_control_loader()
        except Exception as exc:
            result = EscalationResult(
                canonical_workspace_id,
                canonical_chat_id,
                "generation_failed",
                0,
                0,
                "",
                error=str(exc),
            )
            self._record("executive_escalation.generation_failed", result)
            return result

        materials = sorted(set(snapshot.blockers) | set(snapshot.approvals_required))
        digest_key = (
            self.build_digest_key(
                workspace_id=canonical_workspace_id,
                materials=materials,
            )
            if materials
            else ""
        )

        if digest_key and self.dispatcher.is_duplicate(digest_key):
            result = EscalationResult(
                canonical_workspace_id,
                canonical_chat_id,
                "duplicate_suppressed",
                0,
                len(materials),
                digest_key,
            )
            self._record("executive_escalation.suppressed", result)
            return result

        now = self.clock()
        decision = self.interruption_policy.evaluate(
            InterruptionContext(
                workspace_id=canonical_workspace_id,
                recipient_id=canonical_chat_id,
                material_ids=tuple(materials),
                now=now,
                last_sent_at=self.last_sent_store.read(canonical_workspace_id),
            )
        )

        if decision.action == "suppress":
            result = EscalationResult(
                canonical_workspace_id,
                canonical_chat_id,
                "no_new_material",
                0,
                len(materials),
                digest_key,
            )
            self._record("executive_escalation.no_new_material", result)
            return result

        if decision.action == "defer":
            result = EscalationResult(
                canonical_workspace_id,
                canonical_chat_id,
                "rate_limited",
                0,
                len(materials),
                digest_key,
            )
            self._record(
                "executive_escalation.rate_limited",
                result,
                policy_reason=decision.reason,
                retry_at=decision.retry_at.isoformat() if decision.retry_at else None,
            )
            return result

        content = ExecutiveMessageContent(
            kind="material_escalation",
            title="Material escalation — Matt review needed:",
            items=tuple(materials),
            metadata={"workspace_id": canonical_workspace_id},
        )
        target = DeliveryTarget(channel=self.channel, address=canonical_chat_id)
        message = self.renderer.render(content)
        outcome = self.dispatcher.send_with_retry(
            lambda: self.channel_adapter.send(target, message),
            max_attempts=self.max_attempts,
        )
        if outcome.status == "sent":
            self.dispatcher.mark_used(digest_key)
            self.last_sent_store.write(canonical_workspace_id, now)
            result = EscalationResult(
                canonical_workspace_id,
                canonical_chat_id,
                "escalated",
                outcome.attempts,
                len(materials),
                digest_key,
            )
            self._record(
                "executive_escalation.sent",
                result,
                policy_reason=decision.reason,
            )
            return result

        result = EscalationResult(
            canonical_workspace_id,
            canonical_chat_id,
            "delivery_failed",
            outcome.attempts,
            len(materials),
            digest_key,
            error=outcome.error,
        )
        self._record(
            "executive_escalation.delivery_failed",
            result,
            policy_reason=decision.reason,
        )
        return result

    @staticmethod
    def build_digest_key(*, workspace_id: str, materials: Iterable[str]) -> str:
        digest = hashlib.sha256("\n".join(materials).encode("utf-8")).hexdigest()
        return f"{workspace_id.strip()}:material:{digest}"

    def _record(
        self,
        event_type: str,
        result: EscalationResult,
        *,
        policy_reason: str | None = None,
        retry_at: str | None = None,
    ) -> None:
        payload = {
            "event_type": event_type,
            "recorded_at": self.clock().isoformat(),
            **result.to_dict(),
        }
        if policy_reason is not None:
            payload["interruption_policy_reason"] = policy_reason
        if retry_at is not None:
            payload["retry_at"] = retry_at
        self.record_event(payload)
