from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.inbound_lead_alerts import InboundLeadAlertJournal, InboundLeadAlertService
from runtime.inbound_leads import InboundLead
from runtime.proactive_executive_delivery import FileDeliveryKeyStore


class InboundLeadAlertTests(unittest.TestCase):
    def _service(self, root: Path, sender, *, attempts: int = 3) -> InboundLeadAlertService:
        return InboundLeadAlertService(
            send_message=sender,
            chat_id="founder-chat",
            key_store=FileDeliveryKeyStore(root / "keys.json"),
            journal=InboundLeadAlertJournal(root / "events.jsonl"),
            lock_path=root / "delivery.lock",
            max_attempts=attempts,
        )

    @staticmethod
    def _lead() -> InboundLead:
        return InboundLead.from_mapping({
            "lead_id": "controlled-fieldwork-event",
            "contact": "Controlled Prospect",
            "company": "Controlled Company",
            "email": "prospect@controlled.test",
            "source": "Website",
            "selected_service": "FIELDWORK",
            "business_challenge": "Growth has slowed despite continued marketing investment.",
        })

    def test_delivers_once_with_acknowledgement_and_suppresses_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[tuple[str, str]] = []

            def send(chat_id: str, message: str) -> dict[str, str]:
                calls.append((chat_id, message))
                return {"provider": "telegram", "message_id": "501", "chat_id": chat_id}

            service = self._service(root, send)
            delivered = service.deliver(self._lead())
            replay = service.deliver(self._lead())

            self.assertEqual(delivered.status, "delivered")
            self.assertEqual(delivered.receipt["message_id"], "501")
            self.assertEqual(replay.status, "duplicate_suppressed")
            self.assertEqual(len(calls), 1)
            self.assertIn("Selected service: FIELDWORK", calls[0][1])
            self.assertIn("DISCOVERY", calls[0][1])
            self.assertIn("No external communication or paid research", calls[0][1])
            events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
            self.assertEqual(
                [event["event_type"] for event in events],
                ["inbound_lead_alert.delivered", "inbound_lead_alert.duplicate_suppressed"],
            )

    def test_missing_acknowledgement_is_retried_and_logged_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []

            def send(_chat_id: str, _message: str) -> dict[str, str]:
                calls.append("attempt")
                return {"provider": "telegram"}

            result = self._service(root, send, attempts=2).deliver(self._lead())

            self.assertEqual(result.status, "delivery_failed")
            self.assertEqual(result.attempts, 2)
            self.assertEqual(len(calls), 2)
            self.assertIn("acknowledgement", result.error)
            event = json.loads((root / "events.jsonl").read_text().splitlines()[-1])
            self.assertEqual(event["event_type"], "inbound_lead_alert.delivery_failed")
            self.assertFalse((root / "keys.json").exists())


if __name__ == "__main__":
    unittest.main()
