from __future__ import annotations

import unittest

from runtime.tony_growth_blueprint_review import TonyGrowthBlueprintReviewer


class TonyGrowthBlueprintReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reviewer = TonyGrowthBlueprintReviewer()
        self.blueprint = " ".join(
            [
                "Example Co has grown quickly but its positioning and marketing system are fragmented.",
                "The Growth Blueprint prioritises sharper category framing, a distinctive commercial narrative,",
                "a focused proof architecture and a sequenced demand programme that connects market evidence",
                "to a measurable acquisition path. The first phase should validate the strongest growth tension,",
                "codify the proposition and build one evidence-led outreach narrative before scaling activity.",
            ]
        )

    def strong_evidence(self):
        return {
            "growth_blueprint": self.blueprint,
            "sources": ["https://example.com/about", "https://example.com/news"],
            "evidence_gaps": ["Current conversion rate is not public."],
            "narratiive_fit": "Strong fit: strategic clarity and growth-system challenge.",
            "strategic_growth_opportunity": "Unify positioning and demand generation around one defensible growth narrative.",
            "recommendation": "Advance to Matt approval.",
        }

    def test_complete_evidence_grounded_blueprint_is_ready_for_matt_approval(self):
        review = self.reviewer.review(self.strong_evidence())
        self.assertTrue(review.ready_for_approval)
        self.assertEqual(review.status, "ready_for_approval")
        self.assertTrue(all(review.checks.values()))
        self.assertIn("Matt", review.recommendation)
        self.assertIn("approval gate", review.recommendation)
        self.assertEqual(review.to_dict()["judgement_owner"], "Tony")

    def test_missing_sources_or_gaps_blocks_outreach_preparation(self):
        evidence = self.strong_evidence()
        evidence.pop("sources")
        evidence.pop("evidence_gaps")
        review = self.reviewer.review(evidence)
        self.assertEqual(review.status, "revision_required")
        self.assertIn("source_backed_evidence_present", review.failed_checks)
        self.assertIn("evidence_gaps_explicit", review.failed_checks)
        self.assertIn("Do not prepare outreach yet", review.recommendation)

    def test_stop_recommendation_never_advances_to_approval(self):
        evidence = self.strong_evidence()
        evidence["recommendation"] = "Stop: evidence indicates poor Narratiive fit."
        review = self.reviewer.review(evidence)
        self.assertEqual(review.status, "stop_recommended")
        self.assertFalse(review.ready_for_approval)
        self.assertIn("Do not progress", review.recommendation)

    def test_revise_recommendation_returns_to_preparation(self):
        evidence = self.strong_evidence()
        evidence["recommendation"] = "Revise the proposition evidence before progressing."
        review = self.reviewer.review(evidence)
        self.assertEqual(review.status, "revision_required")
        self.assertFalse(review.ready_for_approval)
        self.assertIn("Claude", review.recommendation)


if __name__ == "__main__":
    unittest.main()
