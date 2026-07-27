from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Iterable, Protocol

from runtime.tony_command_service import CommandResponse


BriefCommand = Callable[[str, Iterable[dict[str, Any]]], CommandResponse]
MessageSender = Callable[[str, str], None]
EventRecorder = Callable[[dict[str, Any]], None]
Clock = Callable[[], datetime]


class DeliveryKeyStore(Protocol):
    def contains(self, key: str) -> bool: ...

    def add(self, key: str) -> None: ...


@dataclass(frozen=True)
class ProactiveDeliveryResult:
    delivery_key: str
    status: str
    attempts: int
    command: str
    workspace_id: str
    chat_id: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_key": self.delivery_key,
            "status": self.status,
            "attempts": self.attempts,
            "command": self.command,
            "workspace_id": self.workspace_id,
            "chat_id": self.chat_id,
            "error": self.error,
        }


class InMemoryDeliveryKeyStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def contains(self, key: str) -> bool:
        return key in self._keys

    def add(self, key: str) -> None:
        self._keys.add(key)


class ProactiveExecutiveDeliveryService:
    """Deliver trusted executive briefs once, with bounded retries and evidence."""

    VALID_COMMANDS = {"morning", "evening"}

    def __init__(
        self,
        *,
        execute_command: BriefCommand,
        send_message: MessageSender,
        key_store: DeliveryKeyStore,
        record_event: EventRecorder,
        clock: Clock | None = None,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.execute_command = execute_command
        self.send_message = send_message
        self.key_store = key_store
        self.record_event = record_event
        self.clock = clock or datetime.now
        self.max_attempts = max_attempts

    def deliver(
        self,
        *,
        workspace_id: str,
        chat_id: str,
        command: str,
        objects: Iterable[dict[str, Any]] = (),
        delivery_date: date | None = None,
    ) -> ProactiveDeliveryResult:
        canonical_command = command.strip().lower().lstrip("/")
        if canonical_command not in self.VALID_COMMANDS:
            raise ValueError(f"Unsupported proactive command: {command}")
        if not workspace_id.strip():
            raise ValueError("workspace_id is required")
        if not chat_id.strip():
            raise ValueError("chat_id is required")

        scheduled_date = delivery_date or self.clock().date()
        delivery_key = self.build_delivery_key(
            workspace_id=workspace_id,
            command=canonical_command,
            delivery_date=scheduled_date,
        )
        if self.key_store.contains(delivery_key):
            result = ProactiveDeliveryResult(
                delivery_key=delivery_key,
                status="duplicate_suppressed",
                attempts=0,
                command=canonical_command,
                workspace_id=workspace_id,
                chat_id=chat_id,
            )
            self._record("executive_brief.delivery_suppressed", result)
            return result

        response = self.execute_command(f"/{canonical_command}", objects)
        if response.status == "error":
            result = ProactiveDeliveryResult(
                delivery_key=delivery_key,
                status="generation_failed",
                attempts=0,
                command=canonical_command,
                workspace_id=workspace_id,
                chat_id=chat_id,
                error=str(response.data.get("error_code", "executive_brief_untrusted")),
            )
            self._record("executive_brief.delivery_failed", result)
            return result

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.send_message(chat_id, response.message)
            except Exception as exc:  # transport boundary; exact provider errors vary
                last_error = exc
                continue

            self.key_store.add(delivery_key)
            result = ProactiveDeliveryResult(
                delivery_key=delivery_key,
                status="delivered",
                attempts=attempt,
                command=canonical_command,
                workspace_id=workspace_id,
                chat_id=chat_id,
            )
            self._record("executive_brief.delivered", result)
            return result

        result = ProactiveDeliveryResult(
            delivery_key=delivery_key,
            status="delivery_failed",
            attempts=self.max_attempts,
            command=canonical_command,
            workspace_id=workspace_id,
            chat_id=chat_id,
            error=str(last_error) if last_error else "unknown delivery failure",
        )
        self._record("executive_brief.delivery_failed", result)
        return result

    @staticmethod
    def build_delivery_key(
        *, workspace_id: str,
        command: str,
        delivery_date: date,
    ) -> str:
        return f"{workspace_id.strip()}:{command.strip()}:{delivery_date.isoformat()}"

    def _record(self, event_type: str, result: ProactiveDeliveryResult) -> None:
        self.record_event(
            {
                "event_type": event_type,
                "recorded_at": self.clock().isoformat(),
                **result.to_dict(),
            }
        )
