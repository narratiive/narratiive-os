import unittest
from datetime import datetime

from runtime.friday_executive_review import (
    FridayExecutiveReviewService,
    ReviewRecord,
    ReviewRecordType,
)


class FridayExecutiveReviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = FridayExecutiveReviewService()
        self.period_end = datetime.fromisoformat("2026-07-24T18:00:00+01:00")

    @staticmethod
    def record(record_id, occurred_at, record_type, summary, *, workspace_id="narratiive", evidence=("commit:abc",), theme=None):
        return ReviewRecord(record_id, occurred_at, record_type, summary, evidence, workspace_id, theme)

    def test_uses_seven_day_window_and_workspace_scope(self):
        review = self.service.build((
            self.record("inside", "2026-07-20T09:00:00+01:00", ReviewRecordType.COMPLETED, "Inside"),
            self.record("outside", "2026-07-17T17:59:59+01:00", ReviewRecordType.COMPLETED, "Outside"),
            self.record("other", "2026-07-20T09:00:00+01:00", ReviewRecordType.COMPLETED, "Other", workspace_id="other"),
        ), workspace_id="narratiive", period_end=self.period_end)
        self.assertEqual(review.completed_outputs, ("Inside — commit:abc",))

    def test_duplicate_records_are_excluded(self):
        duplicate = self.record("same", "2026-07-20T09:00:00+01:00", ReviewRecordType.WIN, "One win")
        review = self.service.build((duplicate, duplicate), workspace_id="narratiive", period_end=self.period_end)
        self.assertEqual(review.significant_wins, ("One win — commit:abc",))

    def test_patterns_require_three_records_for_established_confidence(self):
        records = tuple(self.record(f"retry-{index}", f"2026-07-{20 + index}T09:00:00+01:00", ReviewRecordType.RETRIED, f"Retry {index}", theme="deployment retries") for index in range(3))
        review = self.service.build(records, workspace_id="narratiive", period_end=self.period_end)
        self.assertEqual(review.patterns[0].confidence, "established")

    def test_pattern_evidence_is_deduplicated(self):
        records = tuple(
            self.record(
                f"retry-{index}",
                f"2026-07-{20 + index}T09:00:00+01:00",
                ReviewRecordType.RETRIED,
                f"Retry {index}",
                evidence=("workflow:runtime-tests",),
                theme="deployment retries",
            )
            for index in range(3)
        )
        review = self.service.build(records, workspace_id="narratiive", period_end=self.period_end)
        self.assertEqual(review.patterns[0].evidence, ("workflow:runtime-tests",))

    def test_blocker_drives_recommendation(self):
        review = self.service.build((self.record("blocked", "2026-07-20T09:00:00+01:00", ReviewRecordType.BLOCKED, "Runtime credential missing"),), workspace_id="narratiive", period_end=self.period_end)
        self.assertIn("oldest recorded blocker", review.next_week_recommendation)

    def test_compact_render_is_bounded(self):
        records = tuple(self.record(f"item-{index}", f"2026-07-{18 + index}T09:00:00+01:00", ReviewRecordType.COMPLETED, "A" * 500) for index in range(5))
        review = self.service.build(records, workspace_id="narratiive", period_end=self.period_end)
        output = review.render_compact(limit=400)
        self.assertLessEqual(len(output), 400)
        self.assertTrue(output.endswith("…"))

    def test_record_requires_evidence(self):
        with self.assertRaisesRegex(ValueError, "non-empty evidence"):
            self.record(
                "missing-evidence",
                "2026-07-20T09:00:00+01:00",
                ReviewRecordType.COMPLETED,
                "Untrusted result",
                evidence=(),
            )

    def test_records_sort_by_actual_time_not_offset_text(self):
        review = self.service.build(
            (
                self.record(
                    "later",
                    "2026-07-20T10:15:00+02:00",
                    ReviewRecordType.COMPLETED,
                    "Later",
                ),
                self.record(
                    "earlier",
                    "2026-07-20T08:30:00+00:00",
                    ReviewRecordType.COMPLETED,
                    "Earlier",
                ),
            ),
            workspace_id="narratiive",
            period_end=self.period_end,
        )
        self.assertEqual(
            review.completed_outputs,
            ("Later — commit:abc", "Earlier — commit:abc"),
        )


if __name__ == "__main__":
    unittest.main()
