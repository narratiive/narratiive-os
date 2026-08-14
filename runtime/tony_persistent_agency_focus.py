from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.tony_agency_focus import TonyAgencyFocusCommandService
from runtime.tony_command_service import CommandResponse


class TonyPersistentAgencyFocusCommandService(TonyAgencyFocusCommandService):
    """Persist the latest ranked executive focus so conversational continuity survives restarts."""

    def __init__(self, command_service, *, store_path: Path | None = None) -> None:
        self.store_path = store_path or Path(".runtime/agency-focus-context.json")
        super().__init__(command_service)
        self._last_priorities = self._load_priorities()

    def _focus_response(self, agency_response: CommandResponse) -> CommandResponse:
        response = super()._focus_response(agency_response)
        self._persist_priorities(self._last_priorities)
        return response

    def _load_priorities(self) -> tuple[dict[str, Any], ...]:
        if not self.store_path.exists():
            return ()
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ()
        if not isinstance(raw, dict):
            return ()
        priorities = raw.get("priorities")
        if not isinstance(priorities, list):
            return ()
        clean = tuple(dict(item) for item in priorities if isinstance(item, dict))
        return clean[:3]

    def _persist_priorities(self, priorities: tuple[dict[str, Any], ...]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"priorities": [dict(item) for item in priorities]}
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)
