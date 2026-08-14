from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.tony_command_service import CommandResponse


class TonyCommercialWatchCommandService:
    """Persist commercial commitments and surface overdue follow-ups proactively."""

    _WATCH_MARKERS = (
        "what needs attention",
        "what needs my attention",
        "anything overdue",
        "what's overdue",
        "whats overdue",
        "commercial follow-up",
        "commercial follow ups",
        "commercial follow-ups",
        "what is stalled",
        "what's stalled",
        "whats stalled",
    )
    _BRIEF_COMMANDS = {"morning", "morning_brief", "standup", "evening", "evening_review", "end_of_day"}

    def __init__(
        self,
        command_service,
        *,
        store_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.command_service = command_service
        self.store_path = store_path or Path(".runtime/commercial-commitments.json")
        self.clock = clock or datetime.now

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        name = lowered.split(" ", 1)[0].lstrip("/") if lowered else ""

        if any(marker in lowered for marker in self._WATCH_MARKERS):
            return self._watch_response()

        response = self.command_service.execute(command, objects)
        self._capture_commitment(response)

        if name in self._BRIEF_COMMANDS:
            return self._augment_brief(response)
        return response

    @staticmethod
    def _add_business_days(start: date, business_days: int) -> date:
        current = start
        remaining = business_days
        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current

    def _capture_commitment(self, response: CommandResponse) -> None:
        if not isinstance(response.data, dict):
            return
        follow_up = response.data.get("follow_up_commitment")
        lead = response.data.get("lead")
        if not isinstance(follow_up, dict) or not isinstance(lead, dict):
            return

        lead_id = str(lead.get("lead_id") or lead.get("id") or "").strip()
        contact = str(lead.get("contact") or lead.get("Contact") or "").strip()
        if not lead_id or not contact:
            return

        now = self.clock()
        due = self._add_business_days(now.date(), 3)
        commitment = {
            "commitment_id": f"outreach-follow-up:{lead_id}",
            "lead_id": lead_id,
            "contact": contact,
            "company": str(lead.get("company") or lead.get("Company") or "").strip(),
            "action": str(follow_up.get("action") or "").strip(),
            "owner": str(follow_up.get("owner") or "Tony").strip() or "Tony",
            "created_at": now.isoformat(),
            "due_on": due.isoformat(),
            "status": "pending",
        }
        commitments = self._read()
        commitments[commitment["commitment_id"]] = commitment
        self._write(commitments)

    def _overdue(self) -> list[dict[str, Any]]:
        today = self.clock().date()
        overdue: list[dict[str, Any]] = []
        for item in self._read().values():
            if str(item.get("status")) != "pending":
                continue
            try:
                due = date.fromisoformat(str(item.get("due_on")))
            except ValueError:
                continue
            if due <= today:
                overdue.append(item)
        return sorted(overdue, key=lambda item: (str(item.get("due_on")), str(item.get("contact"))))

    def _watch_response(self) -> CommandResponse:
        overdue = self._overdue()
        if not overdue:
            return CommandResponse(
                command="commercial_watch",
                status="healthy",
                message="Nothing in the recorded commercial follow-up queue is overdue right now.",
                data={"intent": "review_commercial_commitments", "overdue_count": 0, "overdue": []},
            )

        first = overdue[0]
        company = f" at {first['company']}" if first.get("company") else ""
        if len(overdue) == 1:
            message = (
                f"One commercial follow-up needs attention: {first['contact']}{company} was due on {first['due_on']}. "
                "I recommend checking for a reply and deciding the next move before starting lower-priority work."
            )
        else:
            message = (
                f"{len(overdue)} commercial follow-ups are overdue. Start with {first['contact']}{company}, due {first['due_on']}, "
                "then clear the remaining follow-ups before lower-priority work."
            )
        return CommandResponse(
            command="commercial_watch",
            status="attention",
            message=message,
            data={"intent": "review_commercial_commitments", "overdue_count": len(overdue), "overdue": overdue},
        )

    def _augment_brief(self, response: CommandResponse) -> CommandResponse:
        if response.status == "error":
            return response
        overdue = self._overdue()
        if not overdue:
            return response

        first = overdue[0]
        company = f" at {first['company']}" if first.get("company") else ""
        alert = (
            f"Commercial attention: {len(overdue)} follow-up{'s are' if len(overdue) != 1 else ' is'} overdue; "
            f"start with {first['contact']}{company}, due {first['due_on']}."
        )
        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["commercial_watch"] = {"overdue_count": len(overdue), "overdue": overdue}
        return CommandResponse(
            command=response.command,
            status="attention" if response.status == "healthy" else response.status,
            message=f"{response.message}\n\n{alert}",
            data=data,
        )

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.store_path.exists():
            return {}
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, list):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            commitment_id = str(item.get("commitment_id") or "").strip()
            if commitment_id:
                result[commitment_id] = item
        return result

    def _write(self, commitments: dict[str, dict[str, Any]]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = sorted(commitments.values(), key=lambda item: str(item.get("commitment_id")))
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)
