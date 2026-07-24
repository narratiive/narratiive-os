import unittest

from runtime.mission_control import (
    ConnectionStatus,
    MissionControlBuilder,
    WorkstreamStatus,
)
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationFinding, ValidationReport


class MissionControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = MissionControlBuilder()

    @staticmethod
    def progress(*, status="empty", errors=()):
        return ProgressSnapshot(
            status=status,
            campaigns=(),
            validation=ValidationReport(
                status="fail" if errors else "pass",
                objects_validated=0,
                errors=tuple(errors),
                warnings=(),
            ),
        )

    def test_empty_snapshot_is_explicit(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-23T18:00:00Z",
            progress=self.progress(),
        )
        self.assertEqual(snapshot.status, "empty")
        self.assertEqual(snapshot.workstreams, ())
        self.assertEqual(snapshot.connections, ())

    def test_unknown_and_not_connected_are_not_reported_as_healthy(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-23T18:00:00Z",
            progress=self.progress(status="healthy"),
            connections={
                "Google Drive": {"state": "not_connected"},
                "Notion": {},
            },
        )
        self.assertEqual(snapshot.status, "partial")
        self.assertEqual(
            [(item.name, item.state) for item in snapshot.connections],
            [("Google Drive", "not_connected"), ("Notion", "unknown")],
        )

    def test_repository_errors_and_workstream_blockers_are_visible(self) -> None:
        finding = ValidationFinding(
            severity="error",
            code="invalid_status",
            message="invalid",
            object_id="object-1",
        )
        snapshot = self.builder.build(
            generated_at="2026-07-23T18:00:00Z",
            progress=self.progress(status="blocked", errors=(finding,)),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="tony-briefs",
                    title="Tony executive briefs",
                    state="blocked",
                    owner="Tony",
                    next_action="Run live acceptance",
                    blocker="live_service_validation",
                    evidence=("https://example.test/pr/1",),
                ),
            ),
        )
        self.assertEqual(snapshot.status, "blocked")
        self.assertEqual(
            snapshot.blockers,
            (
                "repository:invalid_status",
                "workstream:tony-briefs:live_service_validation",
            ),
        )

    def test_degraded_connections_are_blockers_but_not_connected_is_not(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-23T18:00:00Z",
            progress=self.progress(status="healthy"),
            connections={
                "GitHub": {"state": "connected", "evidence": "commit:abc"},
                "Notion": {"state": "degraded"},
                "Drive": {"state": "not_connected"},
            },
        )
        self.assertEqual(snapshot.status, "blocked")
        self.assertEqual(snapshot.blockers, ("connection:Notion:degraded",))

    def test_snapshot_output_is_deterministically_sorted(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-23T18:00:00Z",
            progress=self.progress(status="healthy"),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="zeta",
                    title="Zeta",
                    state="known",
                    owner="Matt",
                    next_action="Define",
                ),
                WorkstreamStatus(
                    workstream_id="alpha",
                    title="Alpha",
                    state="tested",
                    owner="Tony",
                    next_action="Use",
                ),
            ),
            connections={"Zeta": {"state": "connected"}, "Alpha": {"state": "connected"}},
            approvals_required=("review-b", "review-a", "review-a"),
        )
        self.assertEqual([item.workstream_id for item in snapshot.workstreams], ["alpha", "zeta"])
        self.assertEqual([item.name for item in snapshot.connections], ["Alpha", "Zeta"])
        self.assertEqual(snapshot.approvals_required, ("review-a", "review-b"))

    def test_invalid_states_and_unexplained_blockers_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported connection state"):
            ConnectionStatus(name="Notion", state="working")
        with self.assertRaisesRegex(ValueError, "Blocked workstreams require a blocker"):
            WorkstreamStatus(
                workstream_id="x",
                title="X",
                state="blocked",
                owner="Tony",
                next_action="Resolve",
            )


if __name__ == "__main__":
    unittest.main()
