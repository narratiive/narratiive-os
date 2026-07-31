from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from runtime.executive_trigger import TriggerContext
from runtime.mission_control_change_detection import MissionControlChangeDetector
from runtime.mission_control_proactive_delivery import MissionControlProactiveDelivery
from runtime.proactive_change_detection import FileChangeStateStore, ProactiveChangeDetector

NOW = datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc)


class MissionControlProactiveDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        detector = MissionControlChangeDetector(ProactiveChangeDetector(FileChangeStateStore(Path(self.temp.name) / "state.json")))
        self.escalation = mock.Mock()
        self.escalation.escalate.return_value = SimpleNamespace(status="delivered", attempts=1)
        self.events = []
        self.service = MissionControlProactiveDelivery(detector=detector, escalation_service=self.escalation, record_event=self.events.append)

    def tearDown(self):
        self.temp.cleanup()

    def context(self, source="mission_control_change"):
        return TriggerContext(source=source, correlation_id="mc-1", workspace_id="narratiive", fired_at=NOW)

    def snapshot(self, blockers=(), approvals=()):
        return SimpleNamespace(blockers=tuple(blockers), approvals_required=tuple(approvals))

    def test_new_change_delivers_and_repeat_is_suppressed(self):
        snapshot = self.snapshot(blockers=("github:pr:123:attention",))
        first = self.service.run(context=self.context(), snapshot=snapshot, recipient_id=" Matt ")
        second = self.service.run(context=self.context(), snapshot=snapshot, recipient_id="matt")
        self.assertEqual(first.status, "delivered")
        self.assertEqual(second.status, "suppressed")
        self.escalation.escalate.assert_called_once_with(workspace_id="narratiive", recipient_id="matt")
        self.assertEqual(self.events[0]["correlation_id"], "mc-1")

    def test_removed_blocker_delivers_resolution(self):
        self.service.run(context=self.context(), snapshot=self.snapshot(blockers=("github:connection:attention",)), recipient_id="matt")
        result = self.service.run(context=self.context(), snapshot=self.snapshot(), recipient_id="matt")
        self.assertEqual([change.change_type for change in result.changes], ["blocker_resolved"])
        self.assertEqual(self.escalation.escalate.call_count, 2)

    def test_invalid_trigger_and_recipient_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "mission_control_change"):
            self.service.run(context=self.context("manual"), snapshot=self.snapshot(), recipient_id="matt")
        with self.assertRaisesRegex(ValueError, "recipient_id is required"):
            self.service.run(context=self.context(), snapshot=self.snapshot(), recipient_id=" ")


if __name__ == "__main__":
    unittest.main()
