from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.proactive_change_detection import (
    ChangeDetectionStorageError,
    FileChangeStateStore,
    ProactiveChangeDetector,
    WatchedItem,
)

NOW = datetime(2026, 7, 30, 20, 0, tzinfo=timezone.utc)


class ProactiveChangeDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.json"
        self.detector = ProactiveChangeDetector(FileChangeStateStore(self.path))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_new_item_is_reported_once_and_survives_restart(self) -> None:
        item = WatchedItem("b1", "blocker", "Client approval missing")
        first = self.detector.detect([item], now=NOW)
        restarted = ProactiveChangeDetector(FileChangeStateStore(self.path))
        second = restarted.detect([item], now=NOW + timedelta(minutes=15))
        self.assertEqual([change.change_type for change in first], ["new_blocker"])
        self.assertEqual(second, ())

    def test_resolved_blocker_is_reported_once(self) -> None:
        opened = WatchedItem("b1", "blocker", "Deployment waiting")
        resolved = WatchedItem("b1", "blocker", "Deployment waiting", status="resolved")
        self.detector.detect([opened], now=NOW)
        first = self.detector.detect([resolved], now=NOW + timedelta(minutes=15))
        second = self.detector.detect([resolved], now=NOW + timedelta(minutes=30))
        self.assertEqual([change.change_type for change in first], ["blocker_resolved"])
        self.assertEqual(second, ())

    def test_removed_blocker_is_treated_as_resolved(self) -> None:
        item = WatchedItem("b1", "blocker", "Dependency unavailable")
        self.detector.detect([item], now=NOW)
        changes = self.detector.detect([], now=NOW + timedelta(minutes=15))
        self.assertEqual([change.change_type for change in changes], ["blocker_resolved"])
        self.assertEqual(changes[0].item.status, "resolved")

    def test_commitment_escalates_when_it_becomes_overdue(self) -> None:
        item = WatchedItem(
            "c1",
            "commitment",
            "Prepare Friday review",
            due_at=NOW + timedelta(hours=1),
        )
        first = self.detector.detect([item], now=NOW)
        later = self.detector.detect([item], now=NOW + timedelta(hours=2))
        repeated = self.detector.detect([item], now=NOW + timedelta(hours=3))
        self.assertEqual([change.change_type for change in first], ["new_commitment"])
        self.assertEqual([change.change_type for change in later], ["commitment_overdue"])
        self.assertEqual(repeated, ())

    def test_scopes_are_isolated(self) -> None:
        a = WatchedItem("b1", "blocker", "Creative late", client_id="a", workstream_id="launch")
        b = WatchedItem("b1", "blocker", "Creative late", client_id="b", workstream_id="launch")
        changes = self.detector.detect([a, b], now=NOW)
        self.assertEqual(len(changes), 2)
        self.assertNotEqual(changes[0].notification_key, changes[1].notification_key)

    def test_duplicate_scope_fails_closed(self) -> None:
        item = WatchedItem("b1", "blocker", "Duplicate")
        with self.assertRaisesRegex(ValueError, "duplicate watched item"):
            self.detector.detect([item, item], now=NOW)

    def test_corrupt_state_fails_closed(self) -> None:
        self.path.write_text("invalid", encoding="utf-8")
        with self.assertRaises(ChangeDetectionStorageError):
            self.detector.detect([], now=NOW)

    def test_naive_time_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            self.detector.detect([], now=datetime(2026, 7, 30, 20, 0))


if __name__ == "__main__":
    unittest.main()
