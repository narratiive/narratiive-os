from __future__ import annotations

import unittest
from datetime import datetime, timezone

from runtime.executive_trigger import (
    TriggerContext,
    run_triggered_brief,
    run_triggered_escalation,
)
from runtime.proactive_executive_delivery import EscalationResult, ProactiveDeliveryResult


class FakeEscalationService:
    def __init__(self) -> None:
        self.calls = []

    def escalate(self, *, workspace_id: str, chat_id: str) -> EscalationResult:
        self.calls.append((workspace_id, chat_id))
        return EscalationResult(
            workspace_id=workspace_id,
            chat_id=chat_id,
            status="escalated",
            attempts=1,
            material_count=1,
            digest_key="digest",
        )


class FakeBriefService:
    def __init__(self) -> None:
        self.calls = []

    def deliver(
        self,
        *,
        workspace_id: str,
        chat_id: str,
        command: str,
        delivery_date=None,
    ) -> ProactiveDeliveryResult:
        self.calls.append((workspace_id, chat_id, command, delivery_date))
        return ProactiveDeliveryResult(
            delivery_key="key",
            status="delivered",
            attempts=1,
            command=command,
            workspace_id=workspace_id,
            chat_id=chat_id,
        )


class TriggerContextTests(unittest.TestCase):
    def test_canonicalises_identity_and_preserves_joinable_evidence(self):
        context = TriggerContext(
            source="mission_control_change",
            correlation_id=" change-42 ",
            workspace_id=" narratiive ",
            fired_at=datetime(2026, 7, 31, 7, 0, tzinfo=timezone.utc),
            metadata={" snapshot_id ": " mc-12 "},
        )

        self.assertEqual(context.correlation_id, "change-42")
        self.assertEqual(context.workspace_id, "narratiive")
        self.assertEqual(context.metadata, {"snapshot_id": "mc-12"})
        self.assertEqual(
            context.evidence(),
            {
                "trigger_source": "mission_control_change",
                "correlation_id": "change-42",
                "triggered_at": "2026-07-31T07:00:00+00:00",
                "trigger_metadata": {"snapshot_id": "mc-12"},
            },
        )

    def test_rejects_unjoinable_or_ambiguous_context(self):
        aware = datetime(2026, 7, 31, 7, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "correlation_id is required"):
            TriggerContext("scheduled", " ", "narratiive", aware)
        with self.assertRaisesRegex(ValueError, "workspace_id is required"):
            TriggerContext("scheduled", "run-1", " ", aware)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            TriggerContext("scheduled", "run-1", "narratiive", datetime(2026, 7, 31))
        with self.assertRaisesRegex(ValueError, "metadata"):
            TriggerContext("scheduled", "run-1", "narratiive", aware, {"": "x"})


class TriggerRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = TriggerContext(
            source="scheduled",
            correlation_id="scheduler-2026-07-31-morning",
            workspace_id="narratiive",
            fired_at=datetime(2026, 7, 31, 7, 0, tzinfo=timezone.utc),
        )
        self.events = []

    def test_escalation_entry_points_share_context_and_evidence(self):
        service = FakeEscalationService()
        result = run_triggered_escalation(
            service=service,
            context=self.context,
            recipient_address=" 12345 ",
            record_event=self.events.append,
        )

        self.assertEqual(result.status, "escalated")
        self.assertEqual(service.calls, [("narratiive", "12345")])
        self.assertEqual(self.events[0]["event_type"], "executive_trigger.received")
        self.assertEqual(self.events[0]["correlation_id"], self.context.correlation_id)
        self.assertEqual(self.events[0]["delivery_kind"], "escalation")

    def test_brief_entry_points_use_trigger_date_and_canonical_command(self):
        service = FakeBriefService()
        result = run_triggered_brief(
            service=service,
            context=self.context,
            recipient_address="12345",
            command="/Morning",
            record_event=self.events.append,
        )

        self.assertEqual(result.status, "delivered")
        self.assertEqual(
            service.calls,
            [("narratiive", "12345", "morning", self.context.fired_at.date())],
        )
        self.assertEqual(self.events[0]["command"], "morning")
        self.assertEqual(self.events[0]["correlation_id"], self.context.correlation_id)

    def test_invalid_recipient_or_command_fails_before_delivery(self):
        service = FakeBriefService()
        with self.assertRaisesRegex(ValueError, "recipient_address is required"):
            run_triggered_brief(
                service=service,
                context=self.context,
                recipient_address=" ",
                command="morning",
            )
        with self.assertRaisesRegex(ValueError, "Unsupported proactive command"):
            run_triggered_brief(
                service=service,
                context=self.context,
                recipient_address="12345",
                command="weekly",
            )
        self.assertEqual(service.calls, [])


if __name__ == "__main__":
    unittest.main()
