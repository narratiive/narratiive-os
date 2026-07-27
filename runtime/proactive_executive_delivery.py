from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from runtime.mission_control import MissionControlSnapshot
from runtime.tony_command_service import CommandResponse


BriefCommand = Callable[[str, Iterable[dict[str, Any]]], CommandResponse]
MessageSender = Callable[[str, str], None]
EventRecorder = Callable[[dict[str, Any]], None]
Clock = Callable[[], datetime]
MissionControlLoader = Callable[[], MissionControlSnapshot]


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


class ProactiveDeliveryStorageError(RuntimeError):
    """Raised when durable proactive-delivery evidence is missing or corrupt."""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class FileDeliveryKeyStore:
    """Durable delivery-key set that survives process restarts.

    The scheduled trigger runs as a short-lived process on every invocation, so
    the in-memory store from the deterministic coordinator is not sufficient in
    production: duplicate suppression must persist across runs. Malformed state
    fails closed rather than silently behaving as an empty store, which could
    otherwise cause a duplicate send.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def contains(self, key: str) -> bool:
        return key in self._read()

    def add(self, key: str) -> None:
        keys = self._read()
        if key in keys:
            return
        keys.add(key)
        _atomic_write(
            self.path,
            json.dumps({"keys": sorted(keys)}, indent=2, sort_keys=True) + "\n",
        )

    def _read(self) -> set[str]:
        if not self.path.is_file():
            return set()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProactiveDeliveryStorageError(
                f"delivery key store is corrupt: {self.path}"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise ProactiveDeliveryStorageError(
                f"delivery key store has an unexpected shape: {self.path}"
            )
        return {str(item) for item in payload["keys"]}


@dataclass(frozen=True, slots=True)
class DeliveryStatusRecord:
    """The most recent proactive-delivery outcome, for Mission Control visibility."""

    kind: str
    command: str
    status: str
    recorded_at: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "command": self.command,
            "status": self.status,
            "recorded_at": self.recorded_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeliveryStatusRecord":
        return cls(
            kind=str(data["kind"]),
            command=str(data.get("command", "")),
            status=str(data["status"]),
            recorded_at=str(data["recorded_at"]),
            error=(str(data["error"]) if data.get("error") not in (None, "") else None),
        )


FAILING_DELIVERY_STATUSES = {
    "generation_failed",
    "delivery_failed",
    "configuration_blocked",
}


def describe_delivery_status(record: DeliveryStatusRecord | None) -> dict[str, Any]:
    """Render a Mission Control connection entry from the latest delivery record."""

    if record is None:
        return {
            "state": "not_connected",
            "evidence": "No proactive delivery has been attempted yet.",
        }
    state = "degraded" if record.status in FAILING_DELIVERY_STATUSES else "connected"
    evidence = (
        f"{record.kind}:{record.command} -> {record.status}"
        if record.command
        else f"{record.kind} -> {record.status}"
    )
    if record.error:
        evidence += f" ({record.error})"
    return {"state": state, "evidence": evidence, "last_checked_at": record.recorded_at}


class LatestDeliveryStatusStore:
    """Derived current-state snapshot of the most recent proactive delivery attempt.

    This is not an audit history; it is a small atomic-write current-state file
    in the same style as other repository snapshots. The append-only event log
    remains the immutable evidence trail.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, status: DeliveryStatusRecord) -> None:
        _atomic_write(
            self.path,
            json.dumps(status.to_dict(), indent=2, sort_keys=True) + "\n",
        )

    def read(self) -> DeliveryStatusRecord | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProactiveDeliveryStorageError(
                f"proactive delivery status is corrupt: {self.path}"
            ) from exc
        if not isinstance(data, dict):
            raise ProactiveDeliveryStorageError(
                f"proactive delivery status has an unexpected shape: {self.path}"
            )
        try:
            return DeliveryStatusRecord.from_dict(data)
        except KeyError as exc:
            raise ProactiveDeliveryStorageError(
                f"proactive delivery status is missing a field: {exc}"
            ) from exc


class FileLastEscalationStore:
    """Durable per-workspace last-escalation timestamps for interruption thresholds."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self, workspace_id: str) -> datetime | None:
        value = self._read_all().get(workspace_id)
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ProactiveDeliveryStorageError(
                f"invalid last-escalation timestamp: {value}"
            ) from exc

    def write(self, workspace_id: str, when: datetime) -> None:
        entries = self._read_all()
        entries[workspace_id] = when.isoformat()
        _atomic_write(
            self.path,
            json.dumps(entries, indent=2, sort_keys=True) + "\n",
        )

    def _read_all(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProactiveDeliveryStorageError(
                f"last-escalation store is corrupt: {self.path}"
            ) from exc
        if not isinstance(data, dict):
            raise ProactiveDeliveryStorageError(
                f"last-escalation store has an unexpected shape: {self.path}"
            )
        return {str(key): str(value) for key, value in data.items()}


@dataclass(frozen=True)
class EscalationResult:
    workspace_id: str
    chat_id: str
    status: str
    attempts: int
    material_count: int
    digest_key: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "chat_id": self.chat_id,
            "status": self.status,
            "attempts": self.attempts,
            "material_count": self.material_count,
            "digest_key": self.digest_key,
            "error": self.error,
        }


class MaterialEscalationService:
    """Escalate new Mission Control blockers/approvals to Matt.

    Escalation is content-deduplicated (the same set of blockers/approvals is
    never re-sent) and rate-limited by a minimum interruption interval, so a
    burst of new material events collapses into one bounded, evidence-backed
    message rather than paging Matt once per item.
    """

    def __init__(
        self,
        *,
        mission_control_loader: MissionControlLoader,
        send_message: MessageSender,
        key_store: DeliveryKeyStore,
        last_sent_store: FileLastEscalationStore,
        record_event: EventRecorder,
        clock: Clock | None = None,
        max_attempts: int = 3,
        min_interval_seconds: int = 1800,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.mission_control_loader = mission_control_loader
        self.send_message = send_message
        self.key_store = key_store
        self.last_sent_store = last_sent_store
        self.record_event = record_event
        self.clock = clock or datetime.now
        self.max_attempts = max_attempts
        self.min_interval_seconds = min_interval_seconds

    def escalate(self, *, workspace_id: str, chat_id: str) -> EscalationResult:
        if not workspace_id.strip():
            raise ValueError("workspace_id is required")
        if not chat_id.strip():
            raise ValueError("chat_id is required")

        try:
            snapshot = self.mission_control_loader()
        except Exception as exc:
            result = EscalationResult(
                workspace_id, chat_id, "generation_failed", 0, 0, "", error=str(exc)
            )
            self._record("executive_escalation.generation_failed", result)
            return result

        materials = sorted(set(snapshot.blockers) | set(snapshot.approvals_required))
        if not materials:
            result = EscalationResult(workspace_id, chat_id, "no_new_material", 0, 0, "")
            self._record("executive_escalation.no_new_material", result)
            return result

        digest_key = self.build_digest_key(workspace_id=workspace_id, materials=materials)
        if self.key_store.contains(digest_key):
            result = EscalationResult(
                workspace_id, chat_id, "duplicate_suppressed", 0, len(materials), digest_key
            )
            self._record("executive_escalation.suppressed", result)
            return result

        now = self.clock()
        last_sent = self.last_sent_store.read(workspace_id)
        if last_sent is not None and (now - last_sent).total_seconds() < self.min_interval_seconds:
            result = EscalationResult(
                workspace_id, chat_id, "rate_limited", 0, len(materials), digest_key
            )
            self._record("executive_escalation.rate_limited", result)
            return result

        message = self._render(materials)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.send_message(chat_id, message)
            except Exception as exc:  # transport boundary; exact provider errors vary
                last_error = exc
                continue

            self.key_store.add(digest_key)
            self.last_sent_store.write(workspace_id, now)
            result = EscalationResult(
                workspace_id, chat_id, "escalated", attempt, len(materials), digest_key
            )
            self._record("executive_escalation.sent", result)
            return result

        result = EscalationResult(
            workspace_id,
            chat_id,
            "delivery_failed",
            self.max_attempts,
            len(materials),
            digest_key,
            error=str(last_error) if last_error else "unknown delivery failure",
        )
        self._record("executive_escalation.delivery_failed", result)
        return result

    @staticmethod
    def build_digest_key(*, workspace_id: str, materials: Iterable[str]) -> str:
        digest = hashlib.sha256("\n".join(materials).encode("utf-8")).hexdigest()
        return f"{workspace_id.strip()}:material:{digest}"

    @staticmethod
    def _render(materials: list[str]) -> str:
        lines = ["Material escalation — Matt review needed:"]
        lines.extend(f"- {item}" for item in materials[:10])
        if len(materials) > 10:
            lines.append(f"...and {len(materials) - 10} more.")
        return "\n".join(lines)[:3500]

    def _record(self, event_type: str, result: EscalationResult) -> None:
        self.record_event(
            {
                "event_type": event_type,
                "recorded_at": self.clock().isoformat(),
                **result.to_dict(),
            }
        )
