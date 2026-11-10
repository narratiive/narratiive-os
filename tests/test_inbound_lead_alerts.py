from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.inbound_lead_alerts import InboundLeadAlertJournal, InboundLeadAlertService
from runtime.inbound_leads import InboundLead
from runtime.proactive_executive_delivery import FileDeliveryKeyStore


class InboundLeadAlertTests(unittest.TestCase):
    def _service(self, root: Path, sender) -> InboundLeadAlertService:
        return InboundLeadAlertService(
            send_message=sender,
            chat_id="founder-chat",
            key_store=FileDeliveryKeyStore(root / "keys.json"),
            journal=InboundLeadAlertJournal(root / "events.jsonl"),
            lock_path=root / "delivery.lock",
        )

    @staticmethod
    def _lead() -> InboundLead:
        return InboundLead.from_mapping({
            "lead_id": "controlled-fieldwork-event",
            "contact": "Controlled Prospect",
            "company": "Controlled Company",
            "email": "prospect@controlled.example",
            "source": "Website",
            "selected_service": "FIELDWORK",
            "business_challenge": "Growth depends on accidental discovery.",
        })

    def test_delivers_once_and_suppresses_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[tuple[str, str]] = []

            def send(chat_id: str, message: str) -> dict[str, str]:
                calls.append((chat_id, message))
                return {"provider": "telegram", "message_id": "501"}

            service = self._service(root, send)
            delivered = service.deliver(self._lead())
            replay = service.deliver(self._lead())

            self.assertEqual(delivered.status, "delivered")
            self.assertEqual(replay.status, "duplicate_suppressed")
            self.assertEqual(len(calls), 1)
            self.assertIn("Selected service: FIELDWORK", calls[0][1])
            self.assertIn("No client communication", calls[0][1])

    def test_unknown_provider_outcome_is_terminal_and_not_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []

            def send(_chat_id: str, _message: str) -> dict[str, str]:
                calls.append("attempt")
                raise TimeoutError("outcome unknown")

            service = self._service(root, send)
            failed = service.deliver(self._lead())
            replay = service.deliver(self._lead())

            self.assertEqual(failed.status, "delivery_uncertain")
            self.assertEqual(replay.status, "duplicate_suppressed")
            self.assertEqual(calls, ["attempt"])

    def test_interrupted_delivery_is_closed_as_uncertain_before_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = InboundLeadAlertJournal(root / "events.jsonl")
            lead = self._lead()
            key = f"inbound-lead-alert:{lead.lead_id}"
            journal.append({"event_type": "inbound_lead_alert.delivery_started", "delivery_key": key})
            service = self._service(root, lambda *_args: self.fail("must not resend"))

            result = service.deliver(lead)

            self.assertEqual(result.status, "duplicate_suppressed")
            event_types = [json.loads(line)["event_type"] for line in (root / "events.jsonl").read_text().splitlines()]
            self.assertEqual(event_types[-2:], ["inbound_lead_alert.delivery_uncertain", "inbound_lead_alert.duplicate_suppressed"])


if __name__ == "__main__":
    unittest.main()
