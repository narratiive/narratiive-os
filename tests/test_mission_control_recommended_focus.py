import unittest

from runtime.mission_control import MissionControlBuilder, WorkstreamStatus
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationFinding, ValidationReport


class MissionControlRecommendedFocusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = MissionControlBuilder()

    @staticmethod
    def progress(*, status="healthy", errors=()):
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

    def test_prioritises_blockers_then_approvals_then_workstreams(self) -> None:
        finding = ValidationFinding(
            severity="error",
            code="invalid_status",
            message="invalid",
            object_id="object-1",
        )
        snapshot = self.builder.build(
            generated_at="2026-07-26T13:30:00Z",
            progress=self.progress(status="blocked", errors=(finding,)),
            approvals_required=("review-pr-83",),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="mission-control",
                    title="Mission Control",
                    state="tested",
                    owner="Tony",
                    next_action="Run live acceptance",
                ),
            ),
        )

        self.assertEqual(
            snapshot.recommended_focus,
            (
                "resolve:repository:invalid_status",
                "decide:review-pr-83",
                "advance:mission-control:Run live acceptance",
            ),
        )

    def test_focus_is_bounded_and_deterministic(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-26T13:30:00Z",
            progress=self.progress(),
            approvals_required=("z-review", "a-review"),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="zeta",
                    title="Zeta",
                    state="known",
                    owner="Tony",
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
        )

        self.assertEqual(
            snapshot.recommended_focus,
            (
                "decide:a-review",
                "decide:z-review",
                "advance:alpha:Use",
            ),
        )

    def test_blocked_workstream_is_not_repeated_as_an_advance_action(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-26T13:30:00Z",
            progress=self.progress(status="blocked"),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="tony-runtime",
                    title="Tony runtime",
                    state="blocked",
                    owner="Tony",
                    next_action="Deploy",
                    blocker="live_service_validation",
                ),
            ),
        )

        self.assertEqual(
            snapshot.recommended_focus,
            ("resolve:workstream:tony-runtime:live_service_validation",),
        )

    def test_serialised_snapshot_exposes_recommended_focus(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-26T13:30:00Z",
            progress=self.progress(),
            approvals_required=("approve-copy",),
        )

        self.assertEqual(
            snapshot.to_dict()["recommended_focus"],
            ["decide:approve-copy"],
        )


if __name__ == "__main__":
    unittest.main()
