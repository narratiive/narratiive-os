from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from runtime.mission_control_change_detection import MissionControlChangeDetector
from runtime.proactive_change_detection import FileChangeStateStore, ProactiveChangeDetector

NOW = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)


class MissionControlChangeDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.detector = MissionControlChangeDetector(
            ProactiveChangeDetector(
                FileChangeStateStore(Path(self.temp.name) / "mission-control-changes.json")
            )
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def snapshot(*, blockers=(), approvals=()):
        return SimpleNamespace(
            blockers=tuple(blockers),
            approvals_required=tuple(approvals),
        )

    def test_projects_only_explicit_canonical_material(self) -> None:
        items = self.detector.watched_items(
            workspace_id="narratiive",
            snapshot=self.snapshot(
                blockers=("github:pr:120:merge_conflict",),
                approvals=("github:pr:121:https://github.com/narratiive/narratiive-os/pull/121",),
            ),
        )
        self.assertEqual([item.kind for item in items], ["approval", "blocker"])
        self.assertTrue(all(item.client_id == "narratiive" for item in items))
        self.assertTrue(all(item.workstream_id == "mission-control" for item in items))

    def test_unchanged_snapshot_is_suppressed_across_restart(self) -> None:
        snapshot = self.snapshot(blockers=("repository:manifest_invalid",))
        first = self.detector.detect(
            workspace_id="narratiive", snapshot=snapshot, now=NOW
        )
        restarted = MissionControlChangeDetector(
            ProactiveChangeDetector(
                FileChangeStateStore(Path(self.temp.name) / "mission-control-changes.json")
            )
        )
        second = restarted.detect(
            workspace_id="narratiive",
            snapshot=snapshot,
            now=NOW + timedelta(minutes=30),
        )
        self.assertEqual([change.change_type for change in first], ["new_blocker"])
        self.assertEqual(second, ())

    def test_removed_blocker_becomes_one_resolved_change(self) -> None:
        blocked = self.snapshot(blockers=("connection:github:degraded",))
        healthy = self.snapshot()
        self.detector.detect(workspace_id="narratiive", snapshot=blocked, now=NOW)
        resolved = self.detector.detect(
            workspace_id="narratiive",
            snapshot=healthy,
            now=NOW + timedelta(minutes=15),
        )
        repeated = self.detector.detect(
            workspace_id="narratiive",
            snapshot=healthy,
            now=NOW + timedelta(minutes=30),
        )
        self.assertEqual([change.change_type for change in resolved], ["blocker_resolved"])
        self.assertEqual(repeated, ())

    def test_workspaces_are_isolated(self) -> None:
        snapshot = self.snapshot(approvals=("approve:release",))
        first = self.detector.detect(workspace_id="agency", snapshot=snapshot, now=NOW)
        second = self.detector.detect(workspace_id="client-a", snapshot=snapshot, now=NOW)
        self.assertEqual([change.change_type for change in first], ["new_approval"])
        self.assertEqual([change.change_type for change in second], ["new_approval"])
        self.assertNotEqual(
            first[0].notification_key,
            second[0].notification_key,
        )

    def test_blank_workspace_and_material_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_id is required"):
            self.detector.detect(workspace_id=" ", snapshot=self.snapshot(), now=NOW)
        with self.assertRaisesRegex(ValueError, "must be non-empty"):
            self.detector.watched_items(
                workspace_id="narratiive",
                snapshot=self.snapshot(blockers=(" ",)),
            )


if __name__ == "__main__":
    unittest.main()
