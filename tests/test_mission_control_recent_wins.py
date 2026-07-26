import unittest

from runtime.mission_control import MissionControlBuilder
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class MissionControlRecentWinsTests(unittest.TestCase):
    @staticmethod
    def progress() -> ProgressSnapshot:
        return ProgressSnapshot(
            status="healthy",
            campaigns=(),
            validation=ValidationReport(
                status="pass",
                objects_validated=0,
                errors=(),
                warnings=(),
            ),
        )

    def test_recent_wins_are_explicit_deduplicated_and_sorted(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-26T17:00:00Z",
            progress=self.progress(),
            recent_wins=(
                "pr:85:https://github.test/pull/85",
                "  commit:abc  ",
                "pr:85:https://github.test/pull/85",
                "",
            ),
        )

        self.assertEqual(
            snapshot.recent_wins,
            (
                "commit:abc",
                "pr:85:https://github.test/pull/85",
            ),
        )
        self.assertEqual(
            snapshot.to_dict()["recent_wins"],
            ["commit:abc", "pr:85:https://github.test/pull/85"],
        )

    def test_recent_wins_are_bounded(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-26T17:00:00Z",
            progress=self.progress(),
            recent_wins=("win-6", "win-1", "win-5", "win-2", "win-4", "win-3"),
        )

        self.assertEqual(snapshot.recent_wins, ("win-1", "win-2", "win-3", "win-4", "win-5"))

    def test_builder_does_not_infer_wins_from_healthy_state(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-26T17:00:00Z",
            progress=self.progress(),
        )

        self.assertEqual(snapshot.recent_wins, ())


if __name__ == "__main__":
    unittest.main()
