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
    """Append-only evidence for alert delivery, replay suppression and failure."""

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

    def has_delivery_started(self, delivery_key: str) -> bool:
        if not self.path.is_file():
            return False
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            events = (json.loads(line) for line in lines if line.strip())
            return any(
                event.get("delivery_key") == delivery_key
                and event.get("event_type") == "inbound_lead_alert.delivery_started"
                for event in events
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"inbound alert journal is corrupt: {self.path}") from exc


class InboundLeadAlertService:
    """Send one founder alert from the event-driven lead-ingest boundary."""

    def __init__(
        self,
        *,
        send_message: AlertSender,
        chat_id: str,
        key_store: DeliveryKeyStore,
        journal: InboundLeadAlertJournal,
        lock_path: Path,
        max_attempts: int = 1,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_attempts != 1:
            raise ValueError("Telegram inbound alerts use one at-most-once send attempt")
        self.send_message = send_message
        self.chat_id = chat_id.strip()
        self.key_store = key_store
        self.journal = journal
        self.lock_path = lock_path
        self.max_attempts = max_attempts
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def deliver(self, lead: InboundLead) -> InboundLeadAlertResult:
        key = self.delivery_key(lead)
        if not self._eligible(lead):
            return self._record(InboundLeadAlertResult("not_eligible", key, lead.lead_id, 0))
        if not self.chat_id:
            return self._record(
                InboundLeadAlertResult(
                    "delivery_failed", key, lead.lead_id, 0, error="TONY_TELEGRAM_CHAT_ID is not configured"
                )
            )
        try:
            with WorkspaceDeliveryLock(self.lock_path):
                if self.key_store.contains(key) or self.journal.has_delivery_started(key):
                    return self._record(
                        InboundLeadAlertResult("duplicate_suppressed", key, lead.lead_id, 0)
                    )
                self._record(InboundLeadAlertResult("delivery_started", key, lead.lead_id, 0))
                self.key_store.add(key)
                try:
                    provider_receipt = self.send_message(self.chat_id, self.render(lead))
                except Exception as exc:  # an uncertain send must never be replayed blindly
                    return self._record(
                        InboundLeadAlertResult("delivery_failed", key, lead.lead_id, 1, error=str(exc))
                    )
                message_id = str(provider_receipt.get("message_id") or "").strip()
                if not message_id:
                    return self._record(
                        InboundLeadAlertResult(
                            "delivery_failed",
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
                return self._record(
                    InboundLeadAlertResult("delivered", key, lead.lead_id, 1, receipt=receipt)
                )
        except ProactiveDeliveryLockContended as exc:
            return self._record(
                InboundLeadAlertResult("already_running", key, lead.lead_id, 0, error=str(exc))
            )
        except (ProactiveDeliveryLockError, RuntimeError) as exc:
            return self._record(
                InboundLeadAlertResult("delivery_failed", key, lead.lead_id, 0, error=str(exc))
            )

    @staticmethod
    def delivery_key(lead: InboundLead) -> str:
        return f"inbound-lead-alert:{lead.lead_id.strip()}"

    @staticmethod
    def render(lead: InboundLead) -> str:
        prospect = lead.contact + (f" — {lead.company}" if lead.company else "")
        service = lead.selected_service or "Not stated"
        challenge = " ".join((lead.business_challenge or lead.ai_summary or lead.notes).split())
        if not challenge:
            challenge = "No business challenge was captured."
        return "\n".join(
            (
                "New inbound enquiry",
                f"Prospect: {prospect}",
                f"Business challenge: {challenge}",
                f"Selected service: {service}",
                f"Recommended next action: {lead.recommended_next_action}",
                "Status: confirmed submission; fit is not yet assessed. No external communication or paid research has been initiated.",
            )
        )

    @staticmethod
    def _eligible(lead: InboundLead) -> bool:
        return lead.briefing_classification() in {
            "legitimate_inbound_enquiry",
            "verified_commercial_opportunity",
        }

    def _record(self, result: InboundLeadAlertResult) -> InboundLeadAlertResult:
        self.journal.append(
            {
                "event_type": f"inbound_lead_alert.{result.status}",
                "recorded_at": self.clock().isoformat(),
                **result.to_dict(),
            }
        )
        return result
