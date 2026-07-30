from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class WatchedItem:
    item_id: str
    kind: str
    summary: str
    status: str = "open"
    due_at: datetime | None = None
    client_id: str | None = None
    workstream_id: str | None = None

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("item_id is required")
        if self.kind not in {"blocker", "approval", "commitment"}:
            raise ValueError(f"unsupported watched item kind: {self.kind}")
        if not self.summary.strip():
            raise ValueError("summary is required")
        if self.status not in {"open", "resolved"}:
            raise ValueError(f"unsupported watched item status: {self.status}")
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")

    @property
    def scope_key(self) -> str:
        return ":".join(
            [
                self.client_id or "agency",
                self.workstream_id or "general",
                self.kind,
                self.item_id,
            ]
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "summary": self.summary,
            "status": self.status,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "client_id": self.client_id,
            "workstream_id": self.workstream_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "WatchedItem":
        raw_due = value.get("due_at")
        due_at = datetime.fromisoformat(str(raw_due)) if raw_due else None
        return cls(
            item_id=str(value["item_id"]),
            kind=str(value["kind"]),
            summary=str(value["summary"]),
            status=str(value.get("status", "open")),
            due_at=due_at,
            client_id=str(value["client_id"]) if value.get("client_id") else None,
            workstream_id=(
                str(value["workstream_id"]) if value.get("workstream_id") else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MaterialChange:
    change_type: str
    item: WatchedItem

    @property
    def notification_key(self) -> str:
        return f"{self.change_type}:{self.item.scope_key}"


class ChangeDetectionStorageError(RuntimeError):
    pass


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class FileChangeStateStore:
    """Durable, fail-closed state used by short-lived proactive watch processes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> tuple[dict[str, WatchedItem], set[str]]:
        if not self.path.exists():
            return {}, set()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            raw_items = payload["items"]
            raw_notifications = payload["notifications"]
            if not isinstance(raw_items, list) or not isinstance(raw_notifications, list):
                raise TypeError("invalid state shape")
            items = {
                item.scope_key: item
                for item in (WatchedItem.from_dict(value) for value in raw_items)
            }
            return items, {str(key) for key in raw_notifications}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ChangeDetectionStorageError(
                f"proactive change state is unreadable: {self.path}"
            ) from exc

    def save(
        self,
        items: dict[str, WatchedItem],
        notifications: set[str],
    ) -> None:
        _atomic_write(
            self.path,
            {
                "items": [items[key].to_dict() for key in sorted(items)],
                "notifications": sorted(notifications),
            },
        )


class ProactiveChangeDetector:
    """Find material executive changes and suppress repeat notifications.

    The detector compares a trusted current snapshot with the durable last-seen
    snapshot. It reports new blockers, approvals and commitments, resolved
    blockers, and newly overdue commitments. Notification keys persist across
    process restarts and are scoped by client and workstream.
    """

    def __init__(self, store: FileChangeStateStore) -> None:
        self.store = store

    def detect(
        self,
        current_items: Iterable[WatchedItem],
        *,
        now: datetime | None = None,
    ) -> tuple[MaterialChange, ...]:
        checked_at = now or datetime.now(timezone.utc)
        if checked_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        previous, notified = self.store.load()
        current = self._index(current_items)
        candidates: list[MaterialChange] = []

        for key, item in current.items():
            old = previous.get(key)
            if item.status == "open" and (old is None or old.status != "open"):
                candidates.append(MaterialChange(f"new_{item.kind}", item))
            if (
                item.kind == "commitment"
                and item.status == "open"
                and item.due_at is not None
                and item.due_at < checked_at
            ):
                candidates.append(MaterialChange("commitment_overdue", item))

        for key, old in previous.items():
            new = current.get(key)
            if old.kind == "blocker" and old.status == "open" and (
                new is None or new.status == "resolved"
            ):
                resolved = new or WatchedItem(
                    item_id=old.item_id,
                    kind=old.kind,
                    summary=old.summary,
                    status="resolved",
                    due_at=old.due_at,
                    client_id=old.client_id,
                    workstream_id=old.workstream_id,
                )
                candidates.append(MaterialChange("blocker_resolved", resolved))

        changes = tuple(
            change
            for change in candidates
            if change.notification_key not in notified
        )
        notified.update(change.notification_key for change in changes)
        self.store.save(current, notified)
        return changes

    @staticmethod
    def _index(items: Iterable[WatchedItem]) -> dict[str, WatchedItem]:
        indexed: dict[str, WatchedItem] = {}
        for item in items:
            key = item.scope_key
            if key in indexed:
                raise ValueError(f"duplicate watched item in scope: {key}")
            indexed[key] = item
        return indexed
