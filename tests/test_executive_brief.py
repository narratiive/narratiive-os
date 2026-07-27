import unittest

from runtime.executive_brief import BriefPeriod, ExecutiveBriefService
from runtime.mission_control import MissionControlBuilder, WorkstreamStatus
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationFinding, ValidationReport


class ExecutiveBriefServiceTests(unittest.TestCase):
    @staticmethod
    def progress(status="healthy", warnings=()):
        return ProgressSnapshot(
            status=status,
            campaigns=(),
            validation=ValidationReport(
                status="warn" if warnings else "pass",
                objects_validated=0,
                errors=(),
                warnings=warnings,
            ),
        )

    def setUp(self):
        self.builder = MissionControlBuilder()
        self.service = ExecutiveBriefService()

    def test_morning_brief_limits_and_orders_priorities(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T08:00:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus("used", "Used work", "used", "Tony", "Observe", ("commit:used",)),
                WorkstreamStatus("known", "Known work", "known", "Tony", "Design it"),
                WorkstreamStatus("blocked", "Blocked work", "blocked", "Matt", "Connect service", blocker="credential"),
                WorkstreamStatus("functional", "Functional work", "functional", "Tony", "Add tests"),
            ),
        )
        brief = self.service.build(snapshot, BriefPeriod.MORNING)
        self.assertEqual(len(brief.priorities), 3)
        self.assertTrue(brief.priorities[0].startswith("Blocked work"))
        self.assertTrue(brief.priorities[1].startswith("Functional work"))
        self.assertTrue(brief.priorities[2].startswith("Known work"))
        self.assertEqual(brief.completed, ())
        self.assertEqual(brief.open_items, ())
        self.assertEqual(len(brief.tony_handling), 2)

    def test_evening_brief_separates_completed_remaining_and_carry_forward(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T19:00:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus("tested", "Tested work", "tested", "Tony", "Deploy", ("commit:abc",)),
                WorkstreamStatus("open", "Open work", "functional", "Tony", "Run acceptance"),
            ),
        )
        brief = self.service.build(snapshot, BriefPeriod.EVENING)
        self.assertEqual(brief.priorities, ())
        self.assertEqual(brief.completed, ("Tested work: tested — commit:abc",))
        self.assertEqual(brief.open_items, ("Open work (Tony) — Run acceptance",))
        self.assertEqual(brief.carry_forward, ("Open work (Tony) — Run acceptance",))

    def test_brief_preserves_recorded_blockers_and_approvals(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T08:00:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus("bridge", "Live bridge", "blocked", "Matt", "Add credential", blocker="missing_token"),
            ),
            approvals_required=("approve release",),
        )
        brief = self.service.build(snapshot, BriefPeriod.MORNING)
        self.assertEqual(brief.blockers, ("workstream:bridge:missing_token",))
        self.assertEqual(brief.approvals, ("approve release",))
        self.assertEqual(brief.executive.urgency.value, "today")

    def test_compact_morning_render_uses_managerial_sections(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T08:00:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus("active", "Active work", "functional", "Tony", "Run acceptance"),
            ),
            recent_wins=("Bridge health verified",),
        )
        output = self.service.build(snapshot, BriefPeriod.MORNING).render_compact()
        self.assertIn("Morning brief", output)
        self.assertIn("Today's focus:", output)
        self.assertIn("What changed:", output)
        self.assertIn("Tony is handling:", output)
        self.assertNotIn("Observation:", output)
        self.assertNotIn("GitHub:", output)

    def test_compact_evening_render_contains_only_period_relevant_sections(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T19:00:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus("tested", "Tested work", "tested", "Tony", "Deploy", ("commit:abc",)),
            ),
        )
        output = self.service.build(snapshot, BriefPeriod.EVENING).render_compact()
        self.assertIn("End-of-day review", output)
        self.assertIn("Completed:", output)
        self.assertNotIn("Today's focus:", output)
        self.assertNotIn("Tony is handling:", output)

    def test_system_watchouts_are_separate_from_operational_content(self):
        warning = ValidationFinding(
            code="stale-index",
            message="Index is stale",
            location="repository",
        )
        snapshot = self.builder.build(
            generated_at="2026-07-24T08:00:00Z",
            progress=self.progress(warnings=(warning,)),
            connections={
                "notion": {
                    "state": "not_connected",
                    "evidence": "credential not configured",
                }
            },
        )
        brief = self.service.build(snapshot, BriefPeriod.MORNING)
        self.assertIn("notion: not_connected — credential not configured", brief.system_watchouts)
        self.assertIn("Repository: stale-index", brief.system_watchouts)
        output = brief.render_compact()
        self.assertIn("Watch-outs:", output)
        self.assertNotIn("Tony's recommendation:", output)

    def test_empty_state_does_not_invent_work_or_strategy(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T08:00:00Z",
            progress=self.progress(status="empty"),
        )
        brief = self.service.build(snapshot, BriefPeriod.MORNING)
        self.assertEqual(brief.priorities, ())
        self.assertEqual(brief.completed, ())
        self.assertIn("no active workstream", brief.executive.observation.lower())
        output = brief.render_compact()
        self.assertIn("No evidence-backed operational work is currently recorded.", output)
        self.assertNotIn("Tony's recommendation:", output)

    def test_compact_render_is_bounded(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T08:00:00Z",
            progress=self.progress(),
            workstreams=tuple(
                WorkstreamStatus(
                    f"work-{index}",
                    "A" * 900,
                    "functional",
                    "Tony",
                    "B" * 900,
                )
                for index in range(5)
            ),
        )
        output = self.service.build(snapshot, BriefPeriod.MORNING).render_compact(limit=500)
        self.assertLessEqual(len(output), 500)
        self.assertTrue(output.endswith("…"))


if __name__ == "__main__":
    unittest.main()
