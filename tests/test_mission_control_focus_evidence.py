import unittest

from runtime.mission_control import (
    ExecutiveFocusItem,
    MissionControlBuilder,
    WorkstreamStatus,
)
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationFinding, ValidationReport


class MissionControlFocusEvidenceTests(unittest.TestCase):
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

    def test_focus_details_preserve_legacy_actions_with_evidence_and_confidence(self) -> None:
        finding = ValidationFinding(
            severity="error",
            code="invalid_status",
            message="invalid",
            object_id="object-1",
        )
        snapshot = self.builder.build(
            generated_at="2026-07-27T08:30:00Z",
            progress=self.progress(status="blocked", errors=(finding,)),
            approvals_required=("review-pr-83",),
            risks=("Delivery capacity is constrained",),
        )

        self.assertEqual(
            snapshot.recommended_focus,
            (
                "resolve:repository:invalid_status",
                "decide:review-pr-83",
                "mitigate:Delivery capacity is constrained",
            ),
        )
        self.assertEqual(
            snapshot.recommended_focus_details,
            (
                ExecutiveFocusItem(
                    action="resolve:repository:invalid_status",
                    category="blocker",
                    evidence=("blockers/0",),
                    confidence="high",
                ),
                ExecutiveFocusItem(
                    action="decide:review-pr-83",
                    category="approval",
                    evidence=("approvals_required/0",),
                    confidence="high",
                ),
                ExecutiveFocusItem(
                    action="mitigate:Delivery capacity is constrained",
                    category="risk",
                    evidence=("risks/0",),
                    confidence="high",
                ),
            ),
        )

    def test_workstream_focus_includes_snapshot_identity_and_source_evidence(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-27T08:30:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="mission-control",
                    title="Mission Control",
                    state="tested",
                    owner="Tony",
                    next_action="Run live acceptance",
                    evidence=("https://github.com/narratiive/narratiive-os/pull/89",),
                ),
            ),
        )

        self.assertEqual(
            snapshot.recommended_focus_details[0].evidence,
            (
                "workstreams/0",
                "https://github.com/narratiive/narratiive-os/pull/89",
            ),
        )

    def test_serialised_focus_details_are_bounded_and_machine_readable(self) -> None:
        snapshot = self.builder.build(
            generated_at="2026-07-27T08:30:00Z",
            progress=self.progress(),
            approvals_required=("z-review", "a-review"),
            opportunities=("Publish the executive view",),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="alpha",
                    title="Alpha",
                    state="tested",
                    owner="Tony",
                    next_action="Use",
                ),
            ),
        )

        payload = snapshot.to_dict()["recommended_focus_details"]
        self.assertEqual(len(payload), 3)
        self.assertEqual(
            payload[0],
            {
                "action": "decide:a-review",
                "category": "approval",
                "evidence": ["approvals_required/0"],
                "confidence": "high",
            },
        )
        self.assertEqual(payload[2]["category"], "opportunity")

    def test_focus_item_rejects_missing_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty evidence"):
            ExecutiveFocusItem(
                action="advance:mission-control:Run live acceptance",
                category="workstream",
                evidence=(),
            )


if __name__ == "__main__":
    unittest.main()
