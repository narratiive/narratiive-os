from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import DispatchHandler, TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyPersistentAutonomousResultCommandService(TonyAutonomousDispatchCommandService):
    """Persist Tony's most recent verified autonomous result across restarts.

    The parent service owns dispatch safety, evidence verification and conversational
    follow-ups. This wrapper makes only already-verified conversational context durable,
    timestamps it, and refuses to answer from stale persisted evidence. Corrupt,
    incomplete or expired state is ignored rather than trusted.
    """

    _REQUIRED_KEYS = {"worker", "dispatch", "evidence", "executive_result", "verified_at"}

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
        clock: Callable[[], datetime] | None = None,
        max_context_age: timedelta = timedelta(hours=8),
    ) -> None:
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_context_age = max_context_age
        super().__init__(command_service, dispatchers=dispatchers)
        self._last_verified_result = self._load_context()

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold()
        if self._last_verified_result is not None and self._context_is_stale(self._last_verified_result):
            was_follow_up = self._matches_follow_up(normalized, self._RESULT_RECALL_MARKERS) or self._matches_follow_up(
                normalized, self._RESULT_RECOMMENDATION_MARKERS
            )
            self._last_verified_result = None
            self._clear_context()
            if was_follow_up:
                return CommandResponse(
                    command="autonomous_result_stale",
                    status="healthy",
                    message=(
                        "That verified worker result is now too old to use as current executive context. "
                        "I would refresh the evidence or re-rank the current agency priorities before acting on it."
                    ),
                    data={
                        "intent": "refresh_stale_autonomous_result",
                        "context_state": "stale",
                        "external_action_taken": False,
                    },
                )

        before = self._last_verified_result
        response = super().execute(command, objects)
        if self._last_verified_result is not None and self._last_verified_result != before:
            if not self._last_verified_result.get("verified_at"):
                self._last_verified_result["verified_at"] = self._now().isoformat()
            self._persist_context(self._last_verified_result)
        return response

    def _load_context(self) -> dict[str, Any] | None:
        if not self.store_path.exists():
            return None
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or not self._REQUIRED_KEYS.issubset(value):
            return None
        if not isinstance(value.get("dispatch"), dict) or not isinstance(value.get("evidence"), dict):
            return None
        worker = str(value.get("worker") or "").strip()
        executive_result = str(value.get("executive_result") or "").strip()
        verified_at = str(value.get("verified_at") or "").strip()
        if not worker or not executive_result or not self._parse_timestamp(verified_at):
            return None
        context = {
            "worker": worker,
            "dispatch": dict(value["dispatch"]),
            "evidence": dict(value["evidence"]),
            "executive_result": executive_result,
            "verified_at": verified_at,
        }
        if self._context_is_stale(context):
            self._clear_context()
            return None
        return context

    def _context_is_stale(self, context: dict[str, Any]) -> bool:
        verified_at = self._parse_timestamp(str(context.get("verified_at") or ""))
        if verified_at is None:
            return True
        age = self._now() - verified_at
        return age < timedelta(0) or age > self.max_context_age

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _persist_context(self, context: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)

    def _clear_context(self) -> None:
        try:
            self.store_path.unlink(missing_ok=True)
        except OSError:
            pass
