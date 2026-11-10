from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from runtime.inbound_leads import InboundLead
from runtime.proactive_executive_delivery import (
    DeliveryKeyStore,
    ProactiveDeliveryLockContended,
    ProactiveDeliveryLockError,
    WorkspaceDeliveryLock,
)


AlertSender = Callable[[str, str], dict[str, Any]]
_TERMINAL_EVENTS = {
    "inbound_lead_alert.delivered",
    "inbound_lead_alert.delivery_failed",
    "inbound_lead_alert.delivery_uncertain",
}


@dataclass(frozen=True, slots=True)
class InboundLeadAlertResult:
    status: str
    delivery_key: str
    lead_id: str
    attempts: int
    receipt: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InboundLeadAlertJournal:
    """Append-only evidence for delivery, suppression, and uncertain outcomes."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def append(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(self.path, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def delivery_state(self, delivery_key: str) -> str:
        if not self.path.is_file():
            return "not_started"
        try:
            events = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"inbound alert journal is corrupt: {self.path}") from exc
        matching = [event for event in events if event.get("delivery_key") == delivery_key]
        if any(event.get("event_type") in _TERMINAL_EVENTS for event in matching):
            return "terminal"
        if any(event.get("event_type") == "inbound_lead_alert.delivery_started" for event in matching):
            return "started_without_terminal"
        return "not_started"


class InboundLeadAlertService:
    """Send one founder-only alert from the authenticated lead-ingest boundary."""

    def __init__(
        self,
        *,
        send_message: AlertSender,
        chat_id: str,
        key_store: DeliveryKeyStore,
        journal: InboundLeadAlertJournal,
        lock_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.send_message = send_message
        self.chat_id = chat_id.strip()
        self.key_store = key_store
        self.journal = journal
        self.lock_path = lock_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def deliver(self, lead: InboundLead) -> InboundLeadAlertResult:
        key = self.delivery_key(lead)
        if not self._eligible(lead):
            return self._record(InboundLeadAlertResult("not_eligible", key, lead.lead_id, 0))
        if not self.chat_id:
            return self._record(
                InboundLeadAlertResult(
                    "configuration_blocked", key, lead.lead_id, 0, error="TONY_TELEGRAM_CHAT_ID is not configured"
                )
            )
        try:
            with WorkspaceDeliveryLock(self.lock_path):
                state = self.journal.delivery_state(key)
                if state == "started_without_terminal":
                    self._record(
                        InboundLeadAlertResult(
                            "delivery_uncertain",
                            key,
                            lead.lead_id,
                            0,
                            error="A prior process stopped after delivery began; the alert will not be replayed blindly",
                        )
                    )
                    return self._record(InboundLeadAlertResult("duplicate_suppressed", key, lead.lead_id, 0))
                if state == "terminal" or self.key_store.contains(key):
                    return self._record(InboundLeadAlertResult("duplicate_suppressed", key, lead.lead_id, 0))
                self._record(InboundLeadAlertResult("delivery_started", key, lead.lead_id, 0))
                self.key_store.add(key)
                try:
                    provider_receipt = self.send_message(self.chat_id, self.render(lead))
                except Exception as exc:
                    return self._record(
                        InboundLeadAlertResult("delivery_uncertain", key, lead.lead_id, 1, error=str(exc))
                    )
                message_id = str(provider_receipt.get("message_id") or "").strip()
                if not message_id:
                    return self._record(
                        InboundLeadAlertResult(
                            "delivery_uncertain",
                            key,
                            lead.lead_id,
                            1,
                            error="Telegram did not return a delivery acknowledgement",
                        )
                    )
                receipt = {
                    "provider": str(provider_receipt.get("provider") or "telegram"),
                    "message_id": message_id,
                    "date": provider_receipt.get("date"),
                }
                return self._record(InboundLeadAlertResult("delivered", key, lead.lead_id, 1, receipt=receipt))
        except ProactiveDeliveryLockContended as exc:
            return self._record(InboundLeadAlertResult("already_running", key, lead.lead_id, 0, error=str(exc)))
        except (ProactiveDeliveryLockError, RuntimeError) as exc:
            return self._record(InboundLeadAlertResult("delivery_failed", key, lead.lead_id, 0, error=str(exc)))

    @staticmethod
    def delivery_key(lead: InboundLead) -> str:
        return f"inbound-lead-alert:{lead.lead_id.strip()}"

    @staticmethod
    def render(lead: InboundLead) -> str:
        prospect = lead.contact + (f" — {lead.company}" if lead.company else "")
        challenge = " ".join((lead.business_challenge or lead.ai_summary or lead.notes).split())
        return "\n".join(
            (
                "New inbound enquiry",
                f"Prospect: {prospect}",
                f"Business challenge: {challenge or 'No business challenge was captured.'}",
                f"Selected service: {lead.selected_service or 'Not stated'}",
                f"Recommended next action: {lead.recommended_next_action}",
                "Status: confirmed submission; fit is not yet assessed. No client communication or paid research has been initiated.",
            )
        )

    @staticmethod
    def _eligible(lead: InboundLead) -> bool:
        return lead.briefing_classification() in {"legitimate_inbound_enquiry", "verified_commercial_opportunity"}

    def _record(self, result: InboundLeadAlertResult) -> InboundLeadAlertResult:
        self.journal.append(
            {"event_type": f"inbound_lead_alert.{result.status}", "recorded_at": self.clock().isoformat(), **result.to_dict()}
        )
        return result
