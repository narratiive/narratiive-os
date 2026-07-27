import unittest

from runtime.mission_control import MissionControlBuilder, WorkstreamStatus
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class MissionControlRisksOpportunitiesTests(unittest.TestCase):
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

    def test_risks_and_opportunities_are_explicit_normalised_and_serialised(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-27T07:30:00Z",
            progress=self.progress(),
            risks=("  client-dependency  ", "client-dependency", ""),
            opportunities=("publish-canonical-proof", "  accelerate-outreach  "),
        )

        self.assertEqual(snapshot.risks, ("client-dependency",))
        self.assertEqual(
            snapshot.opportunities,
            ("accelerate-outreach", "publish-canonical-proof"),
        )
        self.assertEqual(snapshot.to_dict()["risks"], ["client-dependency"])
        self.assertEqual(
            snapshot.to_dict()["opportunities"],
            ["accelerate-outreach", "publish-canonical-proof"],
        )

    def test_risks_and_opportunities_are_bounded(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-27T07:30:00Z",
            progress=self.progress(),
            risks=("risk-6", "risk-1", "risk-5", "risk-2", "risk-4", "risk-3"),
            opportunities=(
                "opportunity-6",
                "opportunity-1",
                "opportunity-5",
                "opportunity-2",
                "opportunity-4",
                "opportunity-3",
            ),
        )

        self.assertEqual(
            snapshot.risks,
            ("risk-1", "risk-2", "risk-3", "risk-4", "risk-5"),
        )
        self.assertEqual(
            snapshot.opportunities,
            (
                "opportunity-1",
                "opportunity-2",
                "opportunity-3",
                "opportunity-4",
                "opportunity-5",
            ),
        )

    def test_builder_does_not_infer_risks_or_opportunities(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-27T07:30:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="growth",
                    title="Growth",
                    state="tested",
                    owner="Tony",
                    next_action="Run outreach",
                ),
            ),
        )

        self.assertEqual(snapshot.risks, ())
        self.assertEqual(snapshot.opportunities, ())

    def test_focus_prioritises_risks_then_opportunities_before_workstreams(self) -> None:
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-27T07:30:00Z",
            progress=self.progress(),
            risks=("retention-gap",),
            opportunities=("launch-proof",),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="growth",
                    title="Growth",
                    state="tested",
                    owner="Tony",
                    next_action="Run outreach",
                ),
            ),
        )

        self.assertEqual(
            snapshot.recommended_focus,
            (
                "mitigate:retention-gap",
                "pursue:launch-proof",
                "advance:growth:Run outreach",
            ),
        )


if __name__ == "__main__":
    unittest.main()
