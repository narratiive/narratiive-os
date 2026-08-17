from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TonyDiscoveryOutcomeTrackingCommandService:
    """Track a verified booked discovery meeting through evidence-backed review.

    A verified Notion `Discovery booked` transition starts a durable watch. Once the
    scheduled slot has ended, Tony may read meeting evidence autonomously from
    Fireflies and ask Claude to prepare an evidence-grounded commercial assessment.
    No CRM stage change, email or other consequential write is performed here.
    """

    CHECK_MARKERS = {
        "check discovery",
        "check the discovery",
        "what happened in discovery",
        "what happened in the discovery",
        "how did discovery go",
        "how did the discovery go",
        "review discovery",
    }

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        active = self.state.get("active") if isinstance(self.state.get("active"), dict) else None
        if active and normalized in self.CHECK_MARKERS:
            return self._check(active)

        response = self.command_service.execute(command, objects)
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("execution_status") == "discovery_commercial_state_sync_verified":
            return self._activate(response)
        return response

    def _activate(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        tracking = data.get("discovery_tracking") if isinstance(data.get("discovery_tracking"), dict) else {}
        event_id = str(tracking.get("calendar_event_id") or data.get("calendar_event_id") or "").strip()
        if not event_id:
            return response
        active = {
            "calendar_event_id": event_id,
            "notion_receipt": str(data.get("notion_receipt") or ""),
            "lead_id": str(tracking.get("lead_id") or ""),
            "contact": str(tracking.get("contact") or ""),
            "company": str(tracking.get("company") or ""),
            "slot": dict(tracking.get("slot") or {}) if isinstance(tracking.get("slot"), dict) else {},
        }
        self.state["active"] = active
        self._persist()
        updated = dict(data)
        updated["discovery_outcome_tracking"] = {"state": "active", "write_actions_allowed": False, **active}
        updated["execution_status"] = "discovery_outcome_tracking_active"
        return CommandResponse(
            response.command,
            response.status,
            response.message + " I am now tracking the discovery outcome separately from the booking itself. After the meeting I can retrieve verified meeting evidence and prepare the next commercial recommendation; I will not advance Notion or send anything from that evidence without the next approval boundary.",
            updated,
        )

    def _check(self, active: dict[str, Any]) -> CommandResponse:
        end = self._slot_end(active)
        if end is not None and self._now() < end:
            return CommandResponse(
                "discovery_outcome",
                "healthy",
                f"The discovery meeting is booked but has not finished yet. I will not infer an outcome before the verified slot ends at {end.isoformat()}.",
                {"execution_status": "discovery_meeting_not_finished", "discovery_outcome_tracking": {"state": "active", **dict(active)}, "external_action_taken": False},
            )

        fireflies = self.dispatchers.get("Fireflies")
        if fireflies is None:
            return self._blocked(active, "discovery_evidence_dispatcher_unavailable", "No live Fireflies dispatcher is configured, so I cannot verify attendance or meeting content yet.")
        read_dispatch = self._fireflies_dispatch(active)
        try:
            evidence = fireflies(dict(read_dispatch))
        except Exception as exc:
            return self._blocked(active, "discovery_evidence_read_failed", f"The meeting-evidence read failed: {exc}")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(read_dispatch, evidence)
        if not verified:
            return self._blocked(active, "discovery_evidence_unverified", f"Fireflies returned data, but it did not satisfy the read-only evidence contract ({reason}).", evidence=evidence)
        if not self._meeting_content(evidence):
            return self._blocked(active, "discovery_evidence_pending", "There is no decision-grade transcript or meeting summary yet, so I will not invent a discovery outcome.", evidence=evidence)

        claude = self.dispatchers.get("Claude")
        if claude is None:
            return self._blocked(active, "discovery_review_dispatcher_unavailable", "Verified meeting evidence exists, but no live Claude dispatcher is configured to prepare the commercial review.", evidence=evidence)
        review_dispatch = self._claude_dispatch(active, evidence)
        try:
            review = claude(dict(review_dispatch))
        except Exception as exc:
            return self._blocked(active, "discovery_review_failed", f"Claude could not prepare the discovery review: {exc}", evidence=evidence)
        review_verified, review_reason = TonyAutonomousDispatchCommandService._verify_evidence(review_dispatch, review)
        if not review_verified:
            return self._blocked(active, "discovery_review_unverified", f"Claude's discovery review did not satisfy the work-product contract ({review_reason}).", evidence=evidence)

        self.state["active"] = None
        self.state["last_completed"] = {**dict(active), "meeting_evidence": dict(evidence), "review_evidence": dict(review), "reviewed_at": self._now().isoformat()}
        self._persist()
        recommendation = self._first_text(review, ("recommended_next_action", "recommendation", "next_action"))
        summary = self._first_text(review, ("summary", "analysis", "work_product", "result"))
        message = "I retrieved verified discovery evidence and reviewed it without changing any external state."
        if summary:
            message += f" {summary}"
        if recommendation:
            message += f" My recommended next move is: {recommendation}"
        message += " Any post-discovery Notion change, proposal send or other consequential action remains separately approval-gated."
        return CommandResponse(
            "discovery_outcome",
            "healthy",
            message,
            {
                "execution_status": "discovery_outcome_review_ready",
                "discovery_outcome": {
                    "state": "reviewed",
                    "calendar_event_id": active.get("calendar_event_id", ""),
                    "lead_id": active.get("lead_id", ""),
                    "contact": active.get("contact", ""),
                    "company": active.get("company", ""),
                    "meeting_evidence": dict(evidence),
                    "review_evidence": dict(review),
                    "recommended_next_action": recommendation,
                    "approval_required_for_next_write": True,
                },
                "external_action_taken": False,
            },
        )

    @staticmethod
    def _fireflies_dispatch(active: dict[str, Any]) -> dict[str, Any]:
        event_id = str(active.get("calendar_event_id") or "")
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Fireflies",
            "instruction": f"Read meeting evidence associated with Calendar event {event_id}. Return transcript or meeting summary, participants, meeting/transcript identifier and source evidence. Read only; do not change any meeting, CRM record or external state.",
            "target": {"lead_id": active.get("lead_id", ""), "contact": active.get("contact", ""), "company": active.get("company", ""), "area": "commercial"},
            "execution_mode": "autonomous_read",
            "expected_evidence": "verified read-only discovery meeting transcript or summary with source identifier",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "discovery_meeting_evidence", "calendar_event_id": event_id},
        }

    @staticmethod
    def _claude_dispatch(active: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Claude",
            "instruction": "Review the verified discovery meeting evidence. Return a concise summary of business need, buying signal, objections/risks, agreed actions, evidence gaps and one recommended next commercial action. Distinguish meeting attendance from commercial success. Do not send anything or update Notion.",
            "target": {"lead_id": active.get("lead_id", ""), "contact": active.get("contact", ""), "company": active.get("company", ""), "area": "commercial"},
            "execution_mode": "autonomous_prepare",
            "expected_evidence": "evidence-grounded post-discovery commercial review",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "post_discovery_commercial_review", "meeting_evidence": dict(evidence)},
        }

    @staticmethod
    def _meeting_content(evidence: Any) -> str:
        return TonyDiscoveryOutcomeTrackingCommandService._first_text(evidence if isinstance(evidence, dict) else {}, ("transcript", "summary", "meeting_summary", "content", "result"))

    @staticmethod
    def _first_text(value: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return " ".join(item.split())
        return ""

    def _slot_end(self, active: dict[str, Any]) -> datetime | None:
        slot = active.get("slot") if isinstance(active.get("slot"), dict) else {}
        raw = str(slot.get("end") or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _blocked(active: dict[str, Any], status: str, message: str, *, evidence: dict[str, Any] | None = None) -> CommandResponse:
        data: dict[str, Any] = {"execution_status": status, "discovery_outcome_tracking": {"state": "active", **dict(active)}, "external_action_taken": False}
        if isinstance(evidence, dict):
            data["meeting_evidence"] = dict(evidence)
        return CommandResponse("discovery_outcome", "healthy", message + " No commercial outcome or external change has been inferred.", data)

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"active": None, "last_completed": None}
        return payload if isinstance(payload, dict) else {"active": None, "last_completed": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)
