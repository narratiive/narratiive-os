import unittest

from runtime.executive_brief import BriefPeriod
from runtime.executive_integration import (
    ExecutiveChangeFilter,
    ExecutivePriorityEngine,
    IntegratedExecutiveBriefService,
)
from runtime.mission_control import MissionControlBuilder, WorkstreamStatus
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class ExecutiveIntegrationTests(unittest.TestCase):
    @staticmethod
    def progress():
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

    def test_client_work_ranks_above_blocked_engineering_work(self):
        client = WorkstreamStatus(
            "client-rave",
            "Rave client deliverable",
            "functional",
            "Tony",
            "Send the approved response",
        )
        engineering = WorkstreamStatus(
            "github-pr-67",
            "GitHub pull request 67",
            "blocked",
            "Tony",
            "Resolve merge conflict",
            blocker="merge conflict",
        )
        ordered = sorted((engineering, client), key=ExecutivePriorityEngine.key)
        self.assertEqual(ordered[0], client)

    def test_change_filter_removes_case_insensitive_duplicates(self):
        self.assertEqual(
            ExecutiveChangeFilter.unique(
                ("Bridge verified", " bridge   verified ", "Newsletter sent"),
                limit=5,
            ),
            ("Bridge verified", "Newsletter sent"),
        )

    def test_live_brief_uses_business_first_priority_order(self):
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-28T08:00:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus(
                    "github-pr-67",
                    "GitHub pull request 67",
                    "blocked",
                    "Tony",
                    "Resolve merge conflict",
                    blocker="merge conflict",
                ),
                WorkstreamStatus(
                    "lead-follow-up",
                    "Revenue lead follow-up",
                    "known",
                    "Tony",
                    "Send proposal",
                ),
                WorkstreamStatus(
                    "client-rave",
                    "Rave client delivery",
                    "functional",
                    "Tony",
                    "Complete response",
                ),
            ),
            recent_wins=("Bridge verified", "bridge verified"),
        )
        brief = IntegratedExecutiveBriefService().build(snapshot, BriefPeriod.MORNING)
        self.assertTrue(brief.priorities[0].startswith("Rave client delivery"))
        self.assertTrue(brief.priorities[1].startswith("Revenue lead follow-up"))
        self.assertTrue(brief.priorities[2].startswith("GitHub pull request 67"))
        self.assertEqual(brief.changed, ("Bridge verified",))


if __name__ == "__main__":
    unittest.main()
