from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.inbound_leads import InboundLead
from runtime.tony_command_service import CommandResponse


Notify = Callable[[str], Any]


class TonyDiscoveryMonitor:
    """Run the existing Discovery services without waiting for a chat command.

    Calendar and Drive access remain read-only.  The only outbound side effect is
    a deduplicated internal notification to Matt; proposal preparation, approval,
    client email and commercial state changes retain their existing gates.
    """

    _QUIET_STATUSES = {
        "discovery_booking_not_found",
        "discovery_meeting_not_finished",
        "discovery_evidence_pending",
    }
    _ACTIONABLE_STATUSES = {
        "post_discovery_proposal_approval_required",
        "post_discovery_no_proposal_recommended",
        "proposal_brief_requires_groundwork_registration",
    }

    def __init__(
        self,
        *,
        discovery_service,
        post_discovery_service,
        leads_loader: Callable[[], Iterable[InboundLead]],
        notify: Notify,
        state_path: Path,
        events_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.discovery_service = discovery_service
        self.post_discovery_service = post_discovery_service
        self.leads_loader = leads_loader
        self.notify = notify
        self.state_path = state_path
        self.events_path = events_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.state = self._load()

    def run(self) -> dict[str, Any]:
        self._notification_error: str | None = None
        retried = self._retry_pending_notification()
        if retried is not None:
            result = {
                "status": retried["status"],
                "lead_id": retried["lead_id"],
                "external_action_taken": False,
                "notification_sent": retried["sent"],
            }
            if self._notification_error:
                result["notification_error"] = self._notification_error
            event_type = (
                "discovery_monitor.notification_retried"
                if retried["sent"] is True
                else "discovery_monitor.notification_retry_pending"
            )
            self._record(event_type, result)
            return result
        active = self._active_tracking()
        adoption: CommandResponse | None = None
        if active is None:
            adoption = self._adopt_calendar_booking()
            active = self._active_tracking()
            if adoption is not None and adoption.data.get("execution_status") == "discovery_outcome_tracking_active":
                self._notify_once(adoption)
                if self._notification_error:
                    result = {
                        "status": "discovery_outcome_tracking_active",
                        "lead_id": self._lead_id(adoption.data),
                        "external_action_taken": False,
                        "notification_sent": False,
                        "notification_error": self._notification_error,
                    }
                    self._record("discovery_monitor.checked", result)
                    return result
        if active is None:
            result = {
                "status": "no_tracked_discovery",
                "external_action_taken": False,
                "notification_sent": False,
            }
            if self._notification_error:
                result["notification_error"] = self._notification_error
            self._record("discovery_monitor.no_tracked_discovery", result)
            return result

        response = self.post_discovery_service.execute("check discovery", ())
        status = str(response.data.get("execution_status") or "unknown")
        notification_sent = False
        if status not in self._QUIET_STATUSES and self._is_actionable(status):
            notification_sent = self._notify_once(response)
        result = {
            "status": status,
            "lead_id": str(active.get("lead_id") or ""),
            "external_action_taken": False,
            "notification_sent": notification_sent,
        }
        if self._notification_error:
            result["notification_error"] = self._notification_error
        self._record("discovery_monitor.checked", result)
        return result

    def _adopt_calendar_booking(self) -> CommandResponse | None:
        now = self._now()
        leads = sorted(
            (lead for lead in self.leads_loader() if self._eligible_lead(lead)),
            key=lambda lead: lead.created_at,
            reverse=True,
        )
        last_response: CommandResponse | None = None
        for lead in leads:
            query = (lead.company or lead.contact).strip()
            if not query:
                continue
            response = self.discovery_service.discover_from_calendar(
                query=query,
                time_min=(now - timedelta(days=14)).isoformat(),
                time_max=(now + timedelta(days=30)).isoformat(),
                expected_email=lead.email,
                lead_id=lead.lead_id,
            )
            last_response = response
            if response.data.get("execution_status") == "discovery_outcome_tracking_active":
                return response
        return last_response

    @staticmethod
    def _eligible_lead(lead: InboundLead) -> bool:
        if lead.disposition not in {"active", "test"}:
            return False
        return lead.briefing_classification() in {
            "legitimate_inbound_enquiry",
            "verified_commercial_opportunity",
            "test_or_rehearsal",
        }

    def _active_tracking(self) -> dict[str, Any] | None:
        value = self.discovery_service.state.get("active")
        return dict(value) if isinstance(value, dict) else None

    def _is_actionable(self, status: str) -> bool:
        return status in self._ACTIONABLE_STATUSES or any(
            marker in status for marker in ("failed", "unavailable", "unverified", "ambiguous", "requires_")
        )

    def _notify_once(self, response: CommandResponse) -> bool:
        data = response.data if isinstance(response.data, dict) else {}
        lead_id = self._lead_id(data)
        status = str(data.get("execution_status") or response.status)
        message = " ".join(str(response.message or "").split())
        digest = hashlib.sha256(f"{lead_id}\0{status}\0{message}".encode("utf-8")).hexdigest()
        delivered = self.state.get("delivered") if isinstance(self.state.get("delivered"), dict) else {}
        if delivered.get(lead_id) == digest:
            return False
        pending = {"lead_id": lead_id, "status": status, "message": message, "digest": digest}
        # Persist before transport. The post-Discovery service may clear its
        # active record while retaining only a pending approval, so the exact
        # founder notification must survive a process restart independently.
        self.state["pending_notification"] = pending
        self._persist()
        return self._deliver_pending(pending)

    def _retry_pending_notification(self) -> dict[str, Any] | None:
        pending = self.state.get("pending_notification")
        if not isinstance(pending, dict):
            return None
        sent = self._deliver_pending(pending)
        return {
            "sent": sent,
            "lead_id": str(pending.get("lead_id") or "unknown"),
            "status": str(pending.get("status") or "unknown"),
        }

    def _deliver_pending(self, pending: dict[str, Any]) -> bool:
        lead_id = str(pending.get("lead_id") or "unknown")
        status = str(pending.get("status") or "unknown")
        message = str(pending.get("message") or "")
        digest = str(pending.get("digest") or "")
        delivered = self.state.get("delivered") if isinstance(self.state.get("delivered"), dict) else {}
        if delivered.get(lead_id) == digest:
            self.state.pop("pending_notification", None)
            self._persist()
            return False
        try:
            self.notify(message)
        except Exception as exc:
            # Leave the persisted outbox record intact. A transient founder-
            # notification failure must remain retryable and must not abort the
            # surrounding proactive escalation watch.
            self._notification_error = str(exc)
            self._record(
                "discovery_monitor.notification_failed",
                {"lead_id": lead_id, "status": status, "digest": digest, "error": str(exc)},
            )
            return False
        delivered[lead_id] = digest
        self.state["delivered"] = delivered
        current = self.state.get("pending_notification")
        if isinstance(current, dict) and current.get("digest") == digest:
            self.state.pop("pending_notification", None)
        self._persist()
        self._record(
            "discovery_monitor.notification_delivered",
            {"lead_id": lead_id, "status": status, "digest": digest},
        )
        return True

    @staticmethod
    def _lead_id(data: dict[str, Any]) -> str:
        for key in ("post_discovery_commercial", "discovery_outcome", "discovery_outcome_tracking"):
            value = data.get(key)
            if isinstance(value, dict) and str(value.get("lead_id") or "").strip():
                return str(value["lead_id"]).strip()
        return "unknown"

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"delivered": {}}
        return value if isinstance(value, dict) else {"delivered": {}}

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def _record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_type": event_type,
            "recorded_at": self._now().isoformat(),
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
