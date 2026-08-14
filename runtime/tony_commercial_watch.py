from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.tony_command_service import CommandResponse


class TonyCommercialWatchCommandService:
    """Persist commercial commitments and surface the most important commercial attention."""

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
    _REPLY_EVENTS = {"reply_received", "inbound_message", "message_received", "gmail_reply"}
    _AUTO_REPLY_MARKERS = (
        "automatic reply",
        "auto reply",
        "autoreply",
        "out of office",
        "away from the office",
        "currently away",
    )
    _DECLINE_MARKERS = (
        "not interested",
        "no thanks",
        "no thank you",
        "not for us",
        "not a fit",
        "please unsubscribe",
        "remove me",
        "we'll pass",
        "we will pass",
    )
    _POSITIVE_MARKERS = (
        "interested",
        "sounds good",
        "tell me more",
        "let's talk",
        "lets talk",
        "book a call",
        "set up a call",
        "schedule a call",
        "happy to chat",
        "worth a conversation",
        "send over",
        "would love to",
    )
    _POSITIVE_REPLY_WINDOW_DAYS = 3

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
        evidence = tuple(objects)
        reply = self._extract_reply(evidence)
        if reply is not None:
            return self._handle_reply(reply)

        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        name = lowered.split(" ", 1)[0].lstrip("/") if lowered else ""

        if any(marker in lowered for marker in self._WATCH_MARKERS):
            return self._watch_response()

        response = self.command_service.execute(command, evidence)
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
            "email": str(lead.get("email") or lead.get("Email") or "").strip(),
            "action": str(follow_up.get("action") or "").strip(),
            "owner": str(follow_up.get("owner") or "Tony").strip() or "Tony",
            "created_at": now.isoformat(),
            "due_on": due.isoformat(),
            "status": "pending",
        }
        commitments = self._read()
        commitments[commitment["commitment_id"]] = commitment
        self._write(commitments)

    def _extract_reply(self, objects: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
        for item in objects:
            if not isinstance(item, dict):
                continue
            candidate = item.get("reply") if isinstance(item.get("reply"), dict) else item
            provider = str(candidate.get("provider") or candidate.get("source") or "").strip().casefold()
            event = str(candidate.get("event") or candidate.get("type") or "").strip().casefold()
            direction = str(candidate.get("direction") or "").strip().casefold()
            if provider == "gmail" and (event in self._REPLY_EVENTS or direction == "inbound"):
                return dict(candidate)
        return None

    def _handle_reply(self, reply: dict[str, Any]) -> CommandResponse:
        lead_id = str(reply.get("lead_id") or reply.get("leadId") or "").strip()
        body = str(reply.get("body") or reply.get("text") or reply.get("snippet") or "").strip()
        subject = str(reply.get("subject") or "").strip()
        combined = f"{subject}\n{body}".casefold()

        commitments = self._read()
        commitment = next(
            (
                item
                for item in commitments.values()
                if str(item.get("status")) == "pending" and lead_id and str(item.get("lead_id")) == lead_id
            ),
            None,
        )

        if commitment is None:
            return CommandResponse(
                command="commercial_reply",
                status="attention",
                message=(
                    "A Gmail reply arrived, but I can't safely match it to a pending commercial follow-up. "
                    "I have not changed any commitment state."
                ),
                data={
                    "intent": "reconcile_unmatched_commercial_reply",
                    "lead_id": lead_id,
                    "commitment_resolved": False,
                    "external_action_taken": False,
                },
            )

        contact = str(commitment.get("contact") or "the lead")
        company = str(commitment.get("company") or "").strip()
        label = f"{contact} at {company}" if company else contact

        if any(marker in combined for marker in self._AUTO_REPLY_MARKERS):
            return CommandResponse(
                command="commercial_reply",
                status="healthy",
                message=(
                    f"An automatic reply arrived from {label}. I have kept the commercial follow-up open because "
                    "an out-of-office response is not evidence of engagement."
                ),
                data={
                    "intent": "ignore_automatic_reply",
                    "lead_id": lead_id,
                    "commitment_id": commitment["commitment_id"],
                    "commitment_status": "pending",
                    "commitment_resolved": False,
                    "external_action_taken": False,
                },
            )

        declined = any(marker in combined for marker in self._DECLINE_MARKERS)
        positive = not declined and any(marker in combined for marker in self._POSITIVE_MARKERS)
        if declined:
            status = "healthy"
            disposition = "declined"
            next_action = "Close the outreach loop unless there is a specific reason to revisit the account later."
            message = (
                f"{label} replied and the message indicates a decline. I have cleared the scheduled follow-up. "
                "No immediate escalation is needed."
            )
        elif positive:
            status = "attention"
            disposition = "positive_intent"
            next_action = "Review the reply now and decide whether to move the opportunity into a discovery conversation."
            message = (
                f"{label} replied with positive commercial intent. I have cleared the scheduled follow-up. "
                "This deserves attention now; I recommend reviewing the reply and deciding whether to move to discovery."
            )
        else:
            status = "healthy"
            disposition = "reply_received"
            next_action = "Review the reply and decide the next commercial action."
            message = (
                f"{label} replied, so I have cleared the scheduled follow-up. I can't justify an urgency call from the "
                "message evidence alone; review it and decide the next commercial action."
            )

        now = self.clock()
        commitment = dict(commitment)
        commitment["status"] = "resolved"
        commitment["resolved_at"] = now.isoformat()
        commitment["resolution_reason"] = "reply_received"
        commitment["disposition"] = disposition
        commitment["recommended_next_action"] = next_action
        commitment["reply"] = {
            "message_id": str(reply.get("message_id") or reply.get("id") or "").strip(),
            "from": str(reply.get("from") or reply.get("sender") or "").strip(),
            "subject": subject,
            "received_at": str(reply.get("received_at") or reply.get("receivedAt") or now.isoformat()).strip(),
            "body_excerpt": " ".join(body.split())[:240],
        }
        commitments[commitment["commitment_id"]] = commitment
        self._write(commitments)

        return CommandResponse(
            command="commercial_reply",
            status=status,
            message=message,
            data={
                "intent": "assess_commercial_reply",
                "lead_id": lead_id,
                "commitment_id": commitment["commitment_id"],
                "commitment_status": "resolved",
                "commitment_resolved": True,
                "disposition": disposition,
                "recommended_next_action": next_action,
                "reply_evidence": commitment["reply"],
                "external_action_taken": False,
            },
        )

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

    def _recent_positive_replies(self) -> list[dict[str, Any]]:
        now = self.clock()
        recent: list[dict[str, Any]] = []
        for item in self._read().values():
            if str(item.get("status")) != "resolved" or str(item.get("disposition")) != "positive_intent":
                continue
            try:
                resolved = datetime.fromisoformat(str(item.get("resolved_at")))
            except ValueError:
                continue
            age = now.date() - resolved.date()
            if 0 <= age.days <= self._POSITIVE_REPLY_WINDOW_DAYS:
                recent.append(item)
        return sorted(recent, key=lambda item: str(item.get("resolved_at")), reverse=True)

    @staticmethod
    def _lead_label(item: dict[str, Any]) -> str:
        contact = str(item.get("contact") or "the lead")
        company = str(item.get("company") or "").strip()
        return f"{contact} at {company}" if company else contact

    def _watch_response(self) -> CommandResponse:
        positive_replies = self._recent_positive_replies()
        overdue = self._overdue()

        if positive_replies:
            first = positive_replies[0]
            label = self._lead_label(first)
            extra = ""
            if overdue:
                extra = f" There {'is' if len(overdue) == 1 else 'are'} also {len(overdue)} overdue follow-up{'s' if len(overdue) != 1 else ''} to clear afterwards."
            message = (
                f"Immediate commercial priority: {label} replied with positive commercial intent. "
                "Review that reply and decide whether to move the opportunity to discovery before lower-priority work."
                f"{extra}"
            )
            return CommandResponse(
                command="commercial_watch",
                status="attention",
                message=message,
                data={
                    "intent": "synthesise_commercial_priorities",
                    "priority": "positive_reply",
                    "positive_reply_count": len(positive_replies),
                    "positive_replies": positive_replies,
                    "overdue_count": len(overdue),
                    "overdue": overdue,
                },
            )

        if not overdue:
            return CommandResponse(
                command="commercial_watch",
                status="healthy",
                message="Nothing in the recorded commercial follow-up queue needs immediate attention right now.",
                data={
                    "intent": "synthesise_commercial_priorities",
                    "priority": None,
                    "positive_reply_count": 0,
                    "positive_replies": [],
                    "overdue_count": 0,
                    "overdue": [],
                },
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
            data={
                "intent": "synthesise_commercial_priorities",
                "priority": "overdue_follow_up",
                "positive_reply_count": 0,
                "positive_replies": [],
                "overdue_count": len(overdue),
                "overdue": overdue,
            },
        )

    def _augment_brief(self, response: CommandResponse) -> CommandResponse:
        if response.status == "error":
            return response
        positive_replies = self._recent_positive_replies()
        overdue = self._overdue()
        if not positive_replies and not overdue:
            return response

        if positive_replies:
            first = positive_replies[0]
            alert = (
                f"Commercial priority: {self._lead_label(first)} replied positively; review the reply and decide whether "
                "to move to discovery before lower-priority work."
            )
            if overdue:
                alert += f" {len(overdue)} overdue follow-up{'s also need' if len(overdue) != 1 else ' also needs'} clearing afterwards."
            priority = "positive_reply"
        else:
            first = overdue[0]
            company = f" at {first['company']}" if first.get("company") else ""
            alert = (
                f"Commercial attention: {len(overdue)} follow-up{'s are' if len(overdue) != 1 else ' is'} overdue; "
                f"start with {first['contact']}{company}, due {first['due_on']}."
            )
            priority = "overdue_follow_up"

        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["commercial_watch"] = {
            "priority": priority,
            "positive_reply_count": len(positive_replies),
            "positive_replies": positive_replies,
            "overdue_count": len(overdue),
            "overdue": overdue,
        }
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
