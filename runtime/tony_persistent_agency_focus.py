from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

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
    _NEXT_STEP_MARKERS = (
        "what next",
        "what's next",
        "whats next",
        "what should we do next",
        "what should i do next",
        "where do we go next",
        "what now",
    )
    _ACTION_RESULT_COMMANDS = {"action_result", "record_action_result", "worker_return"}
    _VERIFIED_RESULT_STATES = {"completed", "executed", "returned", "success", "succeeded"}

    def __init__(
        self,
        command_service,
        *,
        store_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        stall_after: timedelta = timedelta(hours=2),
    ) -> None:
        self.store_path = store_path or Path(".runtime/agency-focus-context.json")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.stall_after = stall_after
        super().__init__(command_service)
        state = self._load_state()
        self._last_priorities = state["priorities"]
        self._pending_action: dict[str, Any] | None = state["pending_action"]
        self._last_completed_action: dict[str, Any] | None = state["last_completed_action"]

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        name = lowered.split(" ", 1)[0].lstrip("/") if lowered else ""
        materialized = tuple(objects)

        if name in self._ACTION_RESULT_COMMANDS:
            return self._record_action_result(materialized)
        if any(marker in lowered for marker in self._ACTION_STATUS_MARKERS):
            if self._pending_action:
                return self._pending_action_status()
            if self._last_completed_action:
                return self._completed_action_status()
        if self._last_completed_action and not self._pending_action and any(
            marker in lowered for marker in self._NEXT_STEP_MARKERS
        ):
            return self._reassess_after_completion(materialized)

        response = super().execute(command, materialized)
        if response.command in {"morning", "evening"}:
            response = self._augment_brief_with_stalled_action(response)
        return response

    def _focus_response(self, agency_response: CommandResponse) -> CommandResponse:
        response = super()._focus_response(agency_response)
        stalled = self._stalled_action_priority()
        if stalled:
            existing = response.data.get("priorities", []) if isinstance(response.data, dict) else []
            priorities = [dict(item) for item in existing if isinstance(item, dict)]
            original_key = str((self._pending_action or {}).get("priority_key") or "")
            priorities = [item for item in priorities if str(item.get("key") or "") != original_key]
            priorities.append(stalled)
            priorities.sort(key=lambda item: (int(item.get("tier", 99)), int(item.get("area_rank", 99)), str(item.get("label") or "")))
            priorities = priorities[:3]
            self._last_priorities = tuple(dict(item) for item in priorities)
            response = self._render_focus_with_priorities(response, priorities)
        self._persist_state()
        return response

    def _prepare_first_priority_action(self) -> CommandResponse:
        priority = dict(self._last_priorities[0])
        priority_key = str(priority.get("key") or "")
        if self._pending_action and str(self._pending_action.get("priority_key") or "") == priority_key:
            return self._pending_action_status(duplicate_request=True)

        if priority.get("reason") == "stalled_delegated_action":
            return self._pending_action_status(duplicate_request=True)

        response = super()._prepare_first_priority_action()
        data = response.data if isinstance(response.data, dict) else {}
        handoff = data.get("execution_handoff") if isinstance(data.get("execution_handoff"), dict) else {}
        worker = str(handoff.get("worker") or "worker")
        status = "awaiting_matt" if worker.casefold() == "matt" else "awaiting_worker_confirmation"
        prepared_at = self._now_utc().isoformat()
        self._pending_action = {
            "action_id": f"{priority_key}:{prepared_at}",
            "priority_key": priority_key,
            "priority": priority,
            "execution_handoff": dict(handoff),
            "status": status,
            "prepared_at": prepared_at,
            "external_action_taken": False,
        }
        self._persist_state()
        return response

    def _record_action_result(self, objects: tuple[dict[str, Any], ...]) -> CommandResponse:
        if not self._pending_action:
            return CommandResponse(
                command="agency_focus_action_result",
                status="attention",
                message="I cannot close an executive action because there is no open prepared action to match this evidence against.",
                data={"intent": "record_executive_action_result", "accepted": False, "reason": "no_pending_action"},
            )

        result = self._extract_action_result(objects)
        if result is None:
            return self._untrusted_action_result("No structured execution result was supplied.")

        expected_id = str(self._pending_action.get("action_id") or "")
        supplied_id = str(result.get("action_id") or result.get("executive_action_id") or "").strip()
        if not supplied_id or supplied_id != expected_id:
            return self._untrusted_action_result("The execution result does not match the currently open action.")

        result_state = str(result.get("status") or result.get("outcome") or "").strip().casefold()
        if result_state not in self._VERIFIED_RESULT_STATES:
            return self._untrusted_action_result("The worker result does not contain a verified completion state.")

        evidence = result.get("evidence")
        if evidence is None or evidence == "" or evidence == [] or evidence == {}:
            return self._untrusted_action_result("Completion evidence is required before I can close the action.")

        completed = dict(self._pending_action)
        completed["status"] = "completed_verified"
        completed["completed_at"] = self._now_utc().isoformat()
        completed["completion_evidence"] = evidence
        completed["result_summary"] = str(result.get("summary") or "").strip()
        completed["external_action_taken"] = bool(result.get("external_action_taken", False))
        self._last_completed_action = completed
        self._pending_action = None
        self._persist_state()

        priority = completed.get("priority") if isinstance(completed.get("priority"), dict) else {}
        label = str(priority.get("label") or "the priority")
        external = " External execution is confirmed by the supplied evidence." if completed["external_action_taken"] else " This confirms the delegated step, not any unverified external action."
        return CommandResponse(
            command="agency_focus_action_result",
            status="healthy",
            message=f"Verified: the prepared action for {label} is complete.{external}",
            data={
                "intent": "record_executive_action_result",
                "accepted": True,
                "execution_status": "completed_verified",
                "completed_action": dict(completed),
                "external_action_taken": completed["external_action_taken"],
            },
        )

    def _reassess_after_completion(self, objects: tuple[dict[str, Any], ...]) -> CommandResponse:
        completed = dict(self._last_completed_action or {})
        completed_priority = completed.get("priority") if isinstance(completed.get("priority"), dict) else {}
        completed_key = str(completed.get("priority_key") or completed_priority.get("key") or "")
        completed_label = str(completed_priority.get("label") or "the last priority")

        agency_response = self.command_service.execute("morning", objects)
        if agency_response.status == "error":
            return agency_response
        focus = self._focus_response(agency_response)
        data = dict(focus.data) if isinstance(focus.data, dict) else {}
        priorities = [dict(item) for item in data.get("priorities", []) if isinstance(item, dict)]

        if not priorities:
            message = (
                f"The verified step for {completed_label} is complete. There is no new verified agency issue demanding attention right now. "
                "I would use the next block to create or advance a commercial opportunity rather than default to internal systems work."
            )
            next_priority = None
        else:
            next_priority = priorities[0]
            next_key = str(next_priority.get("key") or "")
            if completed_key and next_key == completed_key:
                message = (
                    f"The delegated step for {completed_label} is complete, but the underlying business priority is still active on current evidence. "
                    f"Next, {next_priority['action']}"
                )
            else:
                message = (
                    f"The verified step for {completed_label} is complete. The next priority is {next_priority['label']}. "
                    f"{next_priority['action']}"
                )

        return CommandResponse(
            command="agency_focus_next_step",
            status=focus.status,
            message=message,
            data={
                "intent": "reassess_after_completed_action",
                "completed_action": completed,
                "next_priority": dict(next_priority) if next_priority else None,
                "priorities": priorities,
                "external_action_taken": bool(completed.get("external_action_taken", False)),
            },
        )

    @staticmethod
    def _extract_action_result(objects: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
        for item in objects:
            if not isinstance(item, dict):
                continue
            nested = item.get("executive_action_result")
            if isinstance(nested, dict):
                return dict(nested)
            if "action_id" in item or "executive_action_id" in item:
                return dict(item)
        return None

    def _untrusted_action_result(self, reason: str) -> CommandResponse:
        return CommandResponse(
            command="agency_focus_action_result",
            status="attention",
            message=f"I have not closed the action. {reason}",
            data={
                "intent": "record_executive_action_result",
                "accepted": False,
                "reason": reason,
                "pending_action": dict(self._pending_action or {}),
                "external_action_taken": False,
            },
        )

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
                "stalled": self._pending_action_is_stalled(),
            },
        )

    def _completed_action_status(self) -> CommandResponse:
        completed = dict(self._last_completed_action or {})
        priority = completed.get("priority") if isinstance(completed.get("priority"), dict) else {}
        label = str(priority.get("label") or "the last priority")
        return CommandResponse(
            command="agency_focus_action_status",
            status="healthy",
            message=f"The last prepared action for {label} is complete and backed by recorded execution evidence.",
            data={
                "intent": "track_top_agency_priority_action",
                "execution_status": "completed_verified",
                "completed_action": completed,
                "external_action_taken": bool(completed.get("external_action_taken", False)),
            },
        )

    def _stalled_action_priority(self) -> dict[str, Any] | None:
        if not self._pending_action_is_stalled():
            return None
        pending = dict(self._pending_action or {})
        original = pending.get("priority") if isinstance(pending.get("priority"), dict) else {}
        handoff = pending.get("execution_handoff") if isinstance(pending.get("execution_handoff"), dict) else {}
        status = str(pending.get("status") or "awaiting_worker_confirmation")
        worker = str(handoff.get("worker") or "the assigned worker")
        label = str(original.get("label") or "the prepared priority")
        age = self._pending_action_age()
        age_hours = max(0, int(age.total_seconds() // 3600)) if age else 0

        if status == "awaiting_matt":
            action = f"Your decision is still needed before this can progress. It has been waiting for about {age_hours} hour(s)."
            tier = 25
        else:
            action = (
                f"The prepared handoff to {worker} has no execution or return evidence after about {age_hours} hour(s). "
                "Verify the worker state or reissue the handoff before lower-priority internal work."
            )
            tier = 12

        return {
            "key": f"stalled_action:{pending.get('priority_key') or label}",
            "tier": tier,
            "area_rank": int(original.get("area_rank", 4)),
            "area": str(original.get("area") or "operations"),
            "label": f"the stalled action for {label}",
            "action": action,
            "reason": "stalled_delegated_action",
            "source": "executive_action_accountability",
            "requires_matt": status == "awaiting_matt",
            "target": dict(original.get("target") or {}),
        }

    def _augment_brief_with_stalled_action(self, response: CommandResponse) -> CommandResponse:
        stalled = self._stalled_action_priority()
        if not stalled:
            return response
        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["stalled_executive_action"] = dict(stalled)
        message = f"Stalled action: {stalled['label']}. {stalled['action']}\n{response.message}"
        return CommandResponse(
            command=response.command,
            status="attention",
            message=message,
            data=data,
        )

    def _render_focus_with_priorities(self, response: CommandResponse, priorities: list[dict[str, Any]]) -> CommandResponse:
        if not priorities:
            return response
        first = priorities[0]
        lines = [f"Your first priority is {first['label']}. {first['action']}"]
        if len(priorities) > 1:
            lines.append("Then:")
            for priority in priorities[1:]:
                lines.append(f"- {priority['label']} — {priority['action']}")
        lines.append("I would leave engineering or infrastructure work alone unless it is directly blocking one of these agency outcomes.")
        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["priorities"] = [dict(item) for item in priorities]
        data["stalled_executive_action"] = dict(first) if first.get("reason") == "stalled_delegated_action" else self._stalled_action_priority()
        return CommandResponse(
            command=response.command,
            status="attention",
            message="\n".join(lines),
            data=data,
        )

    def _reason_text(self, priority: dict[str, Any]) -> str:
        if str(priority.get("reason") or "") == "stalled_delegated_action":
            return "a priority we already chose and prepared has stopped progressing without execution evidence"
        return super()._reason_text(priority)

    def _pending_action_is_stalled(self) -> bool:
        age = self._pending_action_age()
        return age is not None and age >= self.stall_after

    def _pending_action_age(self) -> timedelta | None:
        if not self._pending_action:
            return None
        value = str(self._pending_action.get("prepared_at") or "").strip()
        if not value:
            return None
        try:
            prepared = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if prepared.tzinfo is None:
            prepared = prepared.replace(tzinfo=timezone.utc)
        return self._now_utc() - prepared.astimezone(timezone.utc)

    def _now_utc(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _load_state(self) -> dict[str, Any]:
        empty = {"priorities": (), "pending_action": None, "last_completed_action": None}
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
        completed = raw.get("last_completed_action")
        clean_completed = dict(completed) if isinstance(completed, dict) else None
        return {
            "priorities": clean_priorities,
            "pending_action": clean_pending,
            "last_completed_action": clean_completed,
        }

    def _persist_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "priorities": [dict(item) for item in self._last_priorities],
            "pending_action": dict(self._pending_action) if self._pending_action else None,
            "last_completed_action": dict(self._last_completed_action) if self._last_completed_action else None,
        }
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)