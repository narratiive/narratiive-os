import unittest
from decimal import Decimal

from runtime.commercial_executive_integration import CommercialExecutiveIntegrator
from runtime.commercial_intelligence import CommercialSnapshot


class CommercialExecutiveIntegrationTests(unittest.TestCase):
    def test_exposes_pipeline_as_mission_control_domain(self) -> None:
        state = CommercialExecutiveIntegrator().integrate(
            CommercialSnapshot(
                pipeline_value=Decimal("12000.00"),
                weighted_pipeline_value=Decimal("5400.00"),
                open_opportunities=3,
                stalled_opportunities=(),
                actions_required=("Follow up Mother Root",),
            )
        )

        domain = state.to_mission_control_domain()

        self.assertEqual(domain["state"], "connected")
        self.assertEqual(domain["summary"]["weighted_pipeline_value"], "5400.00")
        self.assertEqual(domain["summary"]["priorities"], ["Commercial priority: Follow up Mother Root"])
        self.assertIn("weighted_pipeline_value:5400.00", domain["evidence"])

    def test_renders_concise_executive_lines(self) -> None:
        state = CommercialExecutiveIntegrator().integrate(
            CommercialSnapshot(
                pipeline_value=Decimal("10000.00"),
                weighted_pipeline_value=Decimal("3250.00"),
                open_opportunities=2,
                stalled_opportunities=(),
                actions_required=("Send proposal", "Call prospect", "Prepare scope"),
            )
        )

        lines = state.executive_lines(limit=2)

        self.assertEqual(lines[0], "Commercial: 2 open opportunities, weighted pipeline £3,250.00.")
        self.assertEqual(lines[1:], ("Commercial priority: Send proposal", "Commercial priority: Call prospect"))

    def test_empty_pipeline_is_constructive_not_technical(self) -> None:
        state = CommercialExecutiveIntegrator().integrate(
            CommercialSnapshot(
                pipeline_value=Decimal("0.00"),
                weighted_pipeline_value=Decimal("0.00"),
                open_opportunities=0,
                stalled_opportunities=(),
                actions_required=(),
            )
        )

        self.assertEqual(
            state.executive_lines(),
            (
                "Commercial: 0 open opportunities, weighted pipeline £0.00.",
                "No commercial follow-up is currently overdue.",
            ),
        )

    def test_invalid_limit_fails_closed(self) -> None:
        state = CommercialExecutiveIntegrator().integrate(
            CommercialSnapshot(
                pipeline_value=Decimal("0.00"),
                weighted_pipeline_value=Decimal("0.00"),
                open_opportunities=0,
                stalled_opportunities=(),
                actions_required=(),
            )
        )
        with self.assertRaisesRegex(ValueError, "limit must be positive"):
            state.executive_lines(limit=0)


if __name__ == "__main__":
    unittest.main()
