from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from runtime.interruption_policy import (
    FixedCooldownInterruptionPolicy,
    InterruptionContext,
    InterruptionDecision,
)
from runtime.mission_control import MissionControlSnapshot
from runtime.policy_governed_escalation import PolicyGovernedMaterialEscalationService
from runtime.proactive_executive_delivery import (
    FileLastEscalationStore,
    InMemoryDeliveryKeyStore,
)


class RecordingPolicy:
    def __init__(self, decision: InterruptionDecision) -> None:
        self.decision = decision
        self.contexts: list[InterruptionContext] = []

    def evaluate(self, context: InterruptionContext) -> InterruptionDecision:
        self.contexts.append(context)
        return self.decision


def snapshot(*, blockers=(), approvals=()) -> MissionControlSnapshot:
    return MissionControlSnapshot(
        generated_at="2026-07-28T00:00:00Z",
        status="blocked" if blockers else "healthy",
        progress={"status": "healthy"},
        workstreams=(),
        connections=(),
        approvals_required=tuple(approvals),
        blockers=tuple(blockers),
    )


class PolicyGovernedMaterialEscalationTests(TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc)
        self.events: list[dict[str, object]] = []
        self.sent: list[tuple[str, str]] = []
        self.keys = InMemoryDeliveryKeyStore()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.last_sent = FileLastEscalationStore(Path(directory.name) / "last-sent.json")

    def service(self, *, loader, policy, send=None):
        return PolicyGovernedMaterialEscalationService(
            mission_control_loader=loader,
            send_message=send or (lambda recipient, message: self.sent.append((recipient, message))),
            key_store=self.keys,
            last_sent_store=self.last_sent,
            interruption_policy=policy,
            record_event=self.events.append,
            clock=lambda: self.now,
            max_attempts=2,
        )

    def test_policy_receives_canonical_material_and_delivery_history(self) -> None:
        prior = self.now - timedelta(minutes=10)
        self.last_sent.write("narratiive", prior)
        policy = RecordingPolicy(InterruptionDecision("defer", "cooldown_active", self.now))
        service = self.service(
            loader=lambda: snapshot(
                blockers=(" workstream:x:blocked ",),
                approvals=("pr:12", "pr:12"),
            ),
            policy=policy,
        )

        result = service.escalate(workspace_id=" narratiive ", chat_id=" 12345 ")

        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(len(policy.contexts), 1)
        context = policy.contexts[0]
        self.assertEqual(context.workspace_id, "narratiive")
        self.assertEqual(context.recipient_id, "12345")
        self.assertEqual(context.material_ids, ("pr:12", "workstream:x:blocked"))
        self.assertEqual(context.last_sent_at, prior)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.events[-1]["interruption_policy_reason"], "cooldown_active")
        self.assertIn("retry_at", self.events[-1])

    def test_fixed_policy_preserves_existing_cooldown_behaviour(self) -> None:
        self.last_sent.write("narratiive", self.now - timedelta(minutes=10))
        service = self.service(
            loader=lambda: snapshot(blockers=("workstream:x:blocked",)),
            policy=FixedCooldownInterruptionPolicy(min_interval_seconds=1800),
        )

        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(self.sent, [])

    def test_successful_send_advances_history_and_marks_digest_used(self) -> None:
        policy = RecordingPolicy(InterruptionDecision("send_now", "material_available"))
        service = self.service(
            loader=lambda: snapshot(
                blockers=("workstream:x:blocked",), approvals=("pr:12",)
            ),
            policy=policy,
        )

        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "escalated")
        self.assertEqual(self.last_sent.read("narratiive"), self.now)
        self.assertTrue(self.keys.contains(result.digest_key))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.events[-1]["interruption_policy_reason"], "material_available")

    def test_failed_send_does_not_advance_history_or_mark_digest(self) -> None:
        def fail(_recipient: str, _message: str) -> None:
            raise ConnectionError("Telegram unavailable")

        service = self.service(
            loader=lambda: snapshot(blockers=("workstream:x:blocked",)),
            policy=RecordingPolicy(InterruptionDecision("send_now", "material_available")),
            send=fail,
        )

        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "delivery_failed")
        self.assertIsNone(self.last_sent.read("narratiive"))
        self.assertFalse(self.keys.contains(result.digest_key))

    def test_duplicate_is_suppressed_before_policy_evaluation(self) -> None:
        policy = RecordingPolicy(InterruptionDecision("send_now", "material_available"))
        loader = lambda: snapshot(blockers=("workstream:x:blocked",))
        service = self.service(loader=loader, policy=policy)

        first = service.escalate(workspace_id="narratiive", chat_id="12345")
        second = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(first.status, "escalated")
        self.assertEqual(second.status, "duplicate_suppressed")
        self.assertEqual(len(policy.contexts), 1)
        self.assertEqual(len(self.sent), 1)

    def test_no_material_is_suppressed_by_policy_without_delivery(self) -> None:
        service = self.service(
            loader=lambda: snapshot(),
            policy=FixedCooldownInterruptionPolicy(),
        )

        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "no_new_material")
        self.assertEqual(result.material_count, 0)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    import unittest

    unittest.main()
