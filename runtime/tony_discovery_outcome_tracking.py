from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]

INTERNAL_EMAIL_DOMAIN = "@narratiive.com"
GEMINI_DRIVE_EVIDENCE_SOURCE = "gemini_drive"
FIREFLIES_EVIDENCE_SOURCE = "fireflies"
_EVIDENCE_SOURCES = {GEMINI_DRIVE_EVIDENCE_SOURCE, FIREFLIES_EVIDENCE_SOURCE}
_SYNC_PREFIX = ("sync", "calendar", "booking")


class TonyDiscoveryOutcomeTrackingCommandService:
    """Track a booked discovery meeting through evidence-backed review.

    A verified Notion `Discovery booked` transition starts a durable watch, and so
    does an explicitly verified existing Calendar booking that Tony did not create
    itself (see `discover_from_calendar`/the "sync calendar booking" command).
    Once the scheduled slot has ended, Tony may read meeting evidence autonomously
    from exactly one explicitly configured source — either Google Drive evidence
    attributable to Gemini, or Fireflies — and ask Claude to prepare an
    evidence-grounded commercial assessment. The two sources are never silently
    substituted for one another. No CRM stage change, email or other consequential
    action is performed here.
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
        evidence_source: str = FIREFLIES_EVIDENCE_SOURCE,
    ) -> None:
        if evidence_source not in _EVIDENCE_SOURCES:
            raise ValueError(f"discovery_evidence_source_unsupported: {evidence_source}")
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.evidence_source = evidence_source
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

        tokens = command.strip().split()
        if len(tokens) >= 4 and tuple(token.casefold() for token in tokens[:3]) == _SYNC_PREFIX:
            query = " ".join(tokens[3:]).strip()
            now = self._now()
            return self.discover_from_calendar(
                query=query,
                time_min=now.isoformat(),
                time_max=(now + timedelta(days=30)).isoformat(),
            )

        response = self.command_service.execute(command, objects)
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("execution_status") == "discovery_commercial_state_sync_verified":
            return self._activate(response)
        return response

    def discover_from_calendar(
        self,
        *,
        query: str,
        time_min: str,
        time_max: str,
        expected_email: str = "",
        lead_id: str = "",
    ) -> CommandResponse:
        """Verify an existing Calendar booking Tony did not create, then adopt it.

        Idempotent and durable: replaying the same query against the same booking
        never duplicates the tracking record, and Tony refuses (fails closed)
        rather than silently overwrite a different booking already being tracked.
        """

        if not query.strip():
            return self._sync_error("discovery_booking_query_required", "I need at least a company or contact name to search Calendar for an existing booking.")
        calendar = self.dispatchers.get("Google Calendar")
        if calendar is None:
            return self._sync_error("discovery_booking_calendar_dispatcher_unavailable", "No live Google Calendar dispatcher is configured, so I cannot verify any existing booking.")
        search = {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Google Calendar",
            "instruction": f"Search Calendar for an existing Discovery booking matching '{query}' between {time_min} and {time_max}. Read only; do not change any event.",
            "execution_mode": "autonomous_read",
            "operation": "search",
            "target": {"query": query, "time_min": time_min, "time_max": time_max},
            "expected_evidence": "verified Calendar event list with bounded identifiers",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "discovery_booking_lookup", "query": query},
        }
        try:
            evidence = calendar(dict(search))
        except Exception as exc:
            return self._sync_error("discovery_booking_calendar_read_failed", f"The Calendar search failed: {exc}")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(search, evidence)
        if not verified:
            return self._sync_error("discovery_booking_calendar_unverified", f"Calendar returned data, but it did not satisfy the read-only evidence contract ({reason}).")

        candidates = [
            event
            for event in evidence.get("events", [])
            if isinstance(event, dict) and str(event.get("event_id") or "").strip() and event.get("status") != "cancelled"
        ]
        if expected_email.strip():
            needle = expected_email.strip().casefold()
            candidates = [event for event in candidates if needle in {str(a).casefold() for a in event.get("attendees", [])}]
        if len(candidates) != 1:
            status = "discovery_booking_ambiguous" if candidates else "discovery_booking_not_found"
            message = (
                f"I found {len(candidates)} Calendar events matching '{query}' in that window, so I will not guess which one is the Discovery booking."
                if candidates
                else f"I could not find a verified Calendar event matching '{query}' in that window."
            )
            return self._sync_error(status, message)

        event = candidates[0]
        event_id = str(event.get("event_id") or "").strip()
        existing_active = self.state.get("active") if isinstance(self.state.get("active"), dict) else None
        if isinstance(existing_active, dict) and existing_active.get("calendar_event_id") == event_id:
            return CommandResponse(
                "discovery_booking_discovery",
                "healthy",
                "I am already tracking this exact Calendar booking; replaying this check did not create a duplicate record.",
                {
                    "execution_status": "discovery_outcome_tracking_active",
                    "discovery_outcome_tracking": {"state": "active", "write_actions_allowed": False, **existing_active},
                    "external_action_taken": False,
                },
            )
        last_completed = self.state.get("last_completed") if isinstance(self.state.get("last_completed"), dict) else None
        if isinstance(last_completed, dict) and last_completed.get("calendar_event_id") == event_id:
            return self._sync_error("discovery_outcome_already_reviewed", "This exact Calendar booking has already been reviewed; I will not reopen tracking for it.")
        if isinstance(existing_active, dict) and existing_active.get("calendar_event_id") != event_id:
            return self._sync_error("discovery_booking_tracking_conflict", "I am already tracking a different Discovery booking; resolve or review that one before adopting this one.")

        contact = next(
            (attendee for attendee in event.get("attendees", []) if isinstance(attendee, str) and INTERNAL_EMAIL_DOMAIN not in attendee.casefold()),
            "",
        )
        active = {
            "calendar_event_id": event_id,
            "notion_receipt": "",
            "lead_id": lead_id or f"calendar:{event_id}",
            "contact": contact,
            "company": query,
            "slot": {"start": str(event.get("start") or ""), "end": str(event.get("end") or "")},
            "source": "calendar_adoption",
            "calendar_evidence": {"summary": str(event.get("summary") or ""), "html_link": str(event.get("html_link") or "")},
        }
        self.state["active"] = active
        self._persist()
        return CommandResponse(
            "discovery_booking_discovery",
            "healthy",
            f"I verified an existing Calendar booking ({event.get('summary') or event_id}) that I did not create, and I am now tracking its Discovery outcome. No commercial state has changed.",
            {
                "execution_status": "discovery_outcome_tracking_active",
                "discovery_outcome_tracking": {"state": "active", "write_actions_allowed": False, **active},
                "external_action_taken": False,
            },
        )

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
            "source": "tony_booking_flow",
        }
        existing = self.state.get("active") if isinstance(self.state.get("active"), dict) else None
        if isinstance(existing, dict) and existing.get("calendar_event_id") == event_id:
            return response
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

        if self.evidence_source == GEMINI_DRIVE_EVIDENCE_SOURCE:
            evidence_result = self._read_gemini_drive_evidence(active)
        else:
            evidence_result = self._read_fireflies_evidence(active)
        if isinstance(evidence_result, CommandResponse):
            return evidence_result
        evidence = evidence_result

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
        self.state["last_completed"] = {**dict(active), "meeting_evidence": dict(evidence), "review_evidence": dict(review), "reviewed_at": self._now().isoformat(), "evidence_source": self.evidence_source}
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
                    "evidence_source": self.evidence_source,
                    "meeting_evidence": dict(evidence),
                    "review_evidence": dict(review),
                    "recommended_next_action": recommendation,
                    "approval_required_for_next_write": True,
                },
                "external_action_taken": False,
            },
        )

    def _read_fireflies_evidence(self, active: dict[str, Any]) -> dict[str, Any] | CommandResponse:
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
        return evidence

    def _read_gemini_drive_evidence(self, active: dict[str, Any]) -> dict[str, Any] | CommandResponse:
        drive = self.dispatchers.get("Google Drive")
        if drive is None:
            return self._blocked(active, "discovery_evidence_drive_dispatcher_unavailable", "No live Google Drive dispatcher is configured, so I cannot read any Gemini meeting notes yet.")
        candidates = self._find_gemini_documents(active, drive)
        if isinstance(candidates, CommandResponse):
            return candidates
        if len(candidates) == 0:
            return self._blocked(active, "discovery_evidence_pending", "No Gemini meeting document matching this exact booking has appeared in Drive yet.")
        if len(candidates) > 1:
            return self._blocked(active, "discovery_evidence_ambiguous", "More than one similarly named Drive document matches this booking's bounded identifiers, so I will not guess which is the genuine Gemini record.")
        file_id = str(candidates[0].get("id") or "")
        export = {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Google Drive",
            "instruction": f"Export the verified Gemini meeting document {file_id} as plain text. Read only.",
            "execution_mode": "autonomous_read",
            "operation": "export",
            "target": {"file_id": file_id},
            "expected_evidence": "verified read-only Gemini meeting transcript or summary with source identifier",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "discovery_meeting_evidence", "calendar_event_id": active.get("calendar_event_id", ""), "file_id": file_id},
        }
        try:
            evidence = drive(dict(export))
        except Exception as exc:
            return self._blocked(active, "discovery_evidence_read_failed", f"The Gemini document read failed: {exc}")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(export, evidence)
        if not verified:
            return self._blocked(active, "discovery_evidence_unverified", f"Drive returned data, but it did not satisfy the read-only evidence contract ({reason}).", evidence=evidence)
        if not self._meeting_content(evidence):
            return self._blocked(active, "discovery_evidence_pending", "There is no decision-grade transcript or meeting summary yet, so I will not invent a discovery outcome.", evidence=evidence)
        enriched = dict(evidence)
        enriched["drive_file_id"] = file_id
        enriched["drive_file_name"] = str(candidates[0].get("name") or "")
        enriched["drive_modified_time"] = str(candidates[0].get("modifiedTime") or "")
        enriched["drive_web_view_link"] = str(candidates[0].get("webViewLink") or "")
        enriched.setdefault("transcript", evidence.get("content"))
        enriched.setdefault("meeting_summary", evidence.get("content"))
        return enriched

    def _find_gemini_documents(self, active: dict[str, Any], drive: DispatchHandler) -> list[dict[str, Any]] | CommandResponse:
        """Match a candidate Gemini document to bounded identifiers only.

        Bounds: the document name must reference the meeting title/company/contact
        this exact booking is tracking, and it must have been modified inside a
        bounded window around the verified slot. A similarly named document that
        falls outside those bounds is never accepted.
        """

        label = str(active.get("company") or active.get("contact") or "").strip()
        if not label:
            return self._blocked(active, "discovery_evidence_lookup_requires_identifier", "This tracked booking has no company or contact name recorded, so I cannot bound a Drive search to it.")
        search = {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Google Drive",
            "instruction": f"Search Drive for a Gemini meeting document naming '{label}'. Read only.",
            "execution_mode": "autonomous_read",
            "operation": "search",
            "target": {"query": label, "max_results": 10},
            "expected_evidence": "verified Drive file list",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "discovery_meeting_document_lookup", "query": label},
        }
        try:
            result = drive(dict(search))
        except Exception as exc:
            return self._blocked(active, "discovery_evidence_read_failed", f"The Drive search failed: {exc}")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(search, result)
        if not verified:
            return self._blocked(active, "discovery_evidence_unverified", f"Drive returned data, but it did not satisfy the read-only evidence contract ({reason}).", evidence=result)
        window_start, window_end = self._evidence_window(active)
        matches = []
        for item in result.get("files", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if label.casefold() not in name.casefold():
                continue
            modified = self._parse_timestamp(item.get("modifiedTime"))
            if modified is not None and window_start is not None and not (window_start <= modified <= window_end):
                continue
            matches.append(item)
        return matches

    def _evidence_window(self, active: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
        end = self._slot_end(active)
        if end is None:
            return None, None
        return end - timedelta(hours=2), end + timedelta(days=2)

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

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

    @staticmethod
    def _sync_error(status: str, message: str) -> CommandResponse:
        return CommandResponse("discovery_booking_discovery", "healthy", message + " Nothing has been tracked or changed.", {"execution_status": status, "external_action_taken": False})

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
