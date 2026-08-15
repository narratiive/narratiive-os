from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import DispatchHandler, TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyPersistentAutonomousResultCommandService(TonyAutonomousDispatchCommandService):
    """Persist Tony's most recent verified autonomous result across restarts.

    The parent service owns dispatch safety, evidence verification and conversational
    follow-ups. This wrapper only makes the already-verified conversational context
    durable. Corrupt or incomplete persisted state is ignored rather than trusted.
    """

    _REQUIRED_KEYS = {"worker", "dispatch", "evidence", "executive_result"}

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
    ) -> None:
        self.store_path = store_path
        super().__init__(command_service, dispatchers=dispatchers)
        self._last_verified_result = self._load_context()

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        before = self._last_verified_result
        response = super().execute(command, objects)
        if self._last_verified_result is not None and self._last_verified_result != before:
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
        if not worker or not executive_result:
            return None
        return {
            "worker": worker,
            "dispatch": dict(value["dispatch"]),
            "evidence": dict(value["evidence"]),
            "executive_result": executive_result,
        }

    def _persist_context(self, context: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)
