from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from runtime.tony_agency_focus import TonyAgencyFocusCommandService
from runtime.tony_command_service import CommandResponse


class TonyPersistentAgencyFocusCommandService(TonyAgencyFocusCommandService):
    """Persist ranked focus and prepared actions so Tony can maintain executive continuity."""

    _ACTION_STATUS_MARKERS = (
        "what's happening with that",
        "whats happening with that",
        "what's happening with the first",
        "whats happening with the first",
        "what's the status",
        "whats the status",
        "status on that",
        "has that been done",
        "did that happen",
        "what are you waiting on",
        "where are we with that",
    )

    def __init__(self, command_service, *, store_path: Path | None = None) -> None:
        self.store_path = store_path or Path(".runtime/agency-focus-context.json")
        super().__init__(command_service)
        state = self._load_state()
        self._last_priorities = state["priorities"]
        self._pending_action: dict[str, Any] | None = state["pending_action"]

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        if self._pending_action and any(marker in lowered for marker in self._ACTION_STATUS_MARKERS):
            return self._pending_action_status()
        return super().execute(command, objects)

    def _focus_response(self, agency_response: CommandResponse) -> CommandResponse:
        response = super()._focus_response(agency_response)
        self._persist_state()
        return response

    def _prepare_first_priority_action(self) -> CommandResponse:
        priority = dict(self._last_priorities[0])
        priority_key = str(priority.get("key") or "")
        if self._pending_action and str(self._pending_action.get("priority_key") or "") == priority_key:
            return self._pending_action_status(duplicate_request=True)

        response = super()._prepare_first_priority_action()
        data = response.data if isinstance(response.data, dict) else {}
        handoff = data.get("execution_handoff") if isinstance(data.get("execution_handoff"), dict) else {}
        worker = str(handoff.get("worker") or "worker")
        status = "awaiting_matt" if worker.casefold() == "matt" else "awaiting_worker_confirmation"
        self._pending_action = {
            "priority_key": priority_key,
            "priority": priority,
            "execution_handoff": dict(handoff),
            "status": status,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "external_action_taken": False,
        }
        self._persist_state()
        return response

    def _pending_action_status(self, *, duplicate_request: bool = False) -> CommandResponse:
        pending = dict(self._pending_action or {})
        priority = pending.get("priority") if isinstance(pending.get("priority"), dict) else {}
        handoff = pending.get("execution_handoff") if isinstance(pending.get("execution_handoff"), dict) else {}
        worker = str(handoff.get("worker") or "the assigned worker")
        action = str(handoff.get("action") or "complete the prepared next step")
        label = str(priority.get("label") or "the priority")
        status = str(pending.get("status") or "awaiting_worker_confirmation")

        if status == "awaiting_matt":
            waiting = f"It is waiting on your decision: {action}."
        else:
            waiting = f"The handoff is prepared for {worker} to {action}, but I do not yet have confirmation that the worker executed it."
        prefix = "I already prepared that action. " if duplicate_request else ""
        message = (
            f"{prefix}{label} is still open. {waiting} "
            "I will not treat it as done until there is evidence of execution or return."
        )
        return CommandResponse(
            command="agency_focus_action_status",
            status="attention",
            message=message,
            data={
                "intent": "track_top_agency_priority_action",
                "pending_action": pending,
                "execution_status": status,
                "external_action_taken": False,
                "duplicate_handoff_suppressed": duplicate_request,
            },
        )

    def _load_state(self) -> dict[str, Any]:
        empty = {"priorities": (), "pending_action": None}
        if not self.store_path.exists():
            return empty
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return empty
        if not isinstance(raw, dict):
            return empty
        priorities = raw.get("priorities")
        clean_priorities = ()
        if isinstance(priorities, list):
            clean_priorities = tuple(dict(item) for item in priorities if isinstance(item, dict))[:3]
        pending = raw.get("pending_action")
        clean_pending = dict(pending) if isinstance(pending, dict) else None
        return {"priorities": clean_priorities, "pending_action": clean_pending}

    def _persist_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "priorities": [dict(item) for item in self._last_priorities],
            "pending_action": dict(self._pending_action) if self._pending_action else None,
        }
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)
