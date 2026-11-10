from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.discovery_monitor import TonyDiscoveryMonitor
from runtime.inbound_leads import InboundLead
from runtime.tony_command_service import CommandResponse


class FakeDiscoveryService:
    def __init__(self) -> None:
        self.state = {"active": None}
        self.adoptions = []

    def discover_from_calendar(self, **values):
        self.adoptions.append(values)
        active = {
            "calendar_event_id": "pimente-event",
            "lead_id": values["lead_id"],
            "company": values["query"],
            "slot": {"end": "2026-11-10T15:30:00Z"},
        }
        self.state["active"] = active
        return CommandResponse(
            "discovery_booking_discovery",
            "healthy",
            "I linked the fictional Pimente Calendar booking and am tracking it.",
            {
                "execution_status": "discovery_outcome_tracking_active",
                "discovery_outcome_tracking": active,
                "external_action_taken": False,
            },
        )


class FakePostDiscoveryService:
    def __init__(self, response: CommandResponse) -> None:
        self.response = response
        self.calls = []

    def execute(self, command, objects):
        self.calls.append(command)
        return self.response


class TonyDiscoveryMonitorTests(unittest.TestCase):
    def _monitor(self, *, post_response, notifications):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        discovery = FakeDiscoveryService()
        lead = InboundLead(
            lead_id="pimente-fictional",
            contact="Synthetic Founder",
            company="Pimente Fictional",
            email="founder@pimente.invalid",
            source="Website",
            disposition="test",
            created_at="2026-11-10T13:27:00Z",
        )
        monitor = TonyDiscoveryMonitor(
            discovery_service=discovery,
            post_discovery_service=FakePostDiscoveryService(post_response),
            leads_loader=lambda: (lead,),
            notify=notifications.append,
            state_path=Path(directory.name) / "state.json",
            events_path=Path(directory.name) / "events.jsonl",
            clock=lambda: datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc),
        )
        return monitor, discovery

    def test_monitor_adopts_booking_checks_call_and_notifies_once_per_state(self):
        notifications = []
        response = CommandResponse(
            "post_discovery_commercial",
            "healthy",
            "The fictional Pimente call is reviewed. Say 'do that' to prepare the internal proposal commission brief.",
            {
                "execution_status": "post_discovery_proposal_approval_required",
                "post_discovery_commercial": {"lead_id": "pimente-fictional"},
                "external_action_taken": False,
            },
        )
        monitor, discovery = self._monitor(post_response=response, notifications=notifications)

        first = monitor.run()
        second = monitor.run()

        self.assertEqual(first["status"], "post_discovery_proposal_approval_required")
        self.assertEqual(len(discovery.adoptions), 1)
        self.assertEqual(discovery.adoptions[0]["expected_email"], "founder@pimente.invalid")
        # One booking-linked message plus one completed-call review message;
        # replay sends neither again.
        self.assertEqual(len(notifications), 2)
        self.assertFalse(second["notification_sent"])

    def test_monitor_stays_quiet_while_gemini_document_is_pending(self):
        notifications = []
        response = CommandResponse(
            "discovery_outcome",
            "healthy",
            "No Gemini meeting document is available yet.",
            {
                "execution_status": "discovery_evidence_pending",
                "discovery_outcome_tracking": {"lead_id": "pimente-fictional"},
                "external_action_taken": False,
            },
        )
        monitor, discovery = self._monitor(post_response=response, notifications=notifications)
        discovery.state["active"] = {
            "calendar_event_id": "pimente-event",
            "lead_id": "pimente-fictional",
            "company": "Pimente Fictional",
            "slot": {"end": "2026-11-10T15:30:00Z"},
        }

        result = monitor.run()

        self.assertEqual(result["status"], "discovery_evidence_pending")
        self.assertEqual(notifications, [])

    def test_notification_failure_is_reported_and_remains_retryable(self):
        response = CommandResponse(
            "post_discovery_commercial",
            "healthy",
            "The fictional Pimente call needs Matt review.",
            {
                "execution_status": "post_discovery_proposal_approval_required",
                "post_discovery_commercial": {"lead_id": "pimente-fictional"},
                "external_action_taken": False,
            },
        )
        attempts = []

        def fail_notification(message):
            attempts.append(message)
            raise TimeoutError("Telegram temporarily unavailable")

        monitor, discovery = self._monitor(post_response=response, notifications=[])
        monitor.notify = fail_notification
        discovery.state["active"] = {
            "calendar_event_id": "pimente-event",
            "lead_id": "pimente-fictional",
            "company": "Pimente Fictional",
            "slot": {"end": "2026-11-10T15:30:00Z"},
        }

        first = monitor.run()
        second = monitor.run()

        self.assertFalse(first["notification_sent"])
        self.assertEqual(first["notification_error"], "Telegram temporarily unavailable")
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
