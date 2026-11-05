from __future__ import annotations

import unittest

from scripts.review_rendered_blueprint import rendered_copy_gaps, rendered_model_is_present, visible_registered_citation_slides


class RenderedBlueprintReviewTests(unittest.TestCase):
    def test_detects_body_clipped_from_rendered_slide(self) -> None:
        expected = [{
            "slide_no": 1,
            "title": "Cover",
            "body": "Cover copy.",
            "takeaway": "Cover takeaway.",
            "layout_type": "single_thesis_page",
        }, {
            "slide_no": 2,
            "title": "The Provocation",
            "body": "The category asks owners to trust claims; evidence must be the starting point.",
            "takeaway": "Resolve the contradiction before buying more attention.",
            "layout_type": "provocation_page",
        }]
        ocr = ["KatKin Growth Blueprint", "The Provocation Resolve the contradiction before buying more attention"]
        self.assertEqual(rendered_copy_gaps(expected, ocr), [{"slide": 2, "missing": ["body ending"]}])

    def test_accepts_expected_title_takeaway_and_body(self) -> None:
        expected = [{
            "slide_no": 1,
            "title": "Cover",
            "body": "Cover copy.",
            "takeaway": "Cover takeaway.",
            "layout_type": "single_thesis_page",
        }, {
            "slide_no": 2,
            "title": "The Provocation",
            "body": "The category asks owners to trust claims; evidence must be the starting point.",
            "takeaway": "Resolve the contradiction before buying more attention.",
            "layout_type": "provocation_page",
        }]
        ocr = [
            "KatKin Growth Blueprint",
            "The Provocation The category asks owners to trust claims; evidence must be the starting point. Resolve the contradiction before buying more attention.",
        ]
        self.assertEqual(rendered_copy_gaps(expected, ocr), [])


if __name__ == "__main__":
    unittest.main()

class DirectorRenderedCopyTests(unittest.TestCase):
    def test_director_cover_and_closing_keep_full_authored_body_visible(self):
        pages = [dict(slide_no=i, title='A precise strategic conclusion',
            body='The authored argument must remain visible through its final essential words.',
            takeaway='A bounded commercial consequence.', layout_type='closing_mandate') for i in (1, 2)]
        complete = ['A precise strategic conclusion The authored argument must remain visible through its final essential words. A bounded commercial consequence.'] * 2
        self.assertEqual(rendered_copy_gaps(pages, complete, director=True), [])
        self.assertEqual(rendered_copy_gaps(pages, ['Missing copy', complete[1]], director=True),
            [{'slide': 1, 'missing': ['body ending']}])

    def test_account_revenue_requires_profit_disclaimer_and_legacy_still_requires_contribution(self):
        account = {"content_data": {"mechanism": "incremental_accounts_year_one"}}
        self.assertTrue(rendered_model_is_present(account, "Year-one revenue. Revenue, not profit."))
        self.assertFalse(rendered_model_is_present(account, "Year-one revenue."))
        self.assertFalse(rendered_model_is_present({}, "Revenue, not profit."))
        self.assertTrue(rendered_model_is_present({}, "Revenue and contribution."))


class RegisteredCitationRegressionTests(unittest.TestCase):
    def test_origin_p1_assumption_citations_require_registered_source_and_exact_visible_label(self):
        register = [{"source_id": name, "title": title, "publisher": "Narratiive",
                     "location": location, "classification": classification}
                    for name, title, location, classification in [
                        ("P1", "Fictional proposal financial assumptions", "inputs/financial-model.md", "assumption"),
                        ("T1", "Rehearsal strategy", "canonical-strategy", "synthetically_reviewed_strategy")]]
        pages = [{"citation_labels": ["P1"]} for _ in range(19)]
        pages[0] = {"citation_labels": ["T1"]}
        pages[17] = {"citation_labels": ["P1", "T1"], "content_data": {"source_register_entries": register}}
        ocr = ["Sources: P1"] * 19
        ocr[0] = "Sources: T1"
        ocr[17] = "Source register P1 T1"
        self.assertEqual(visible_registered_citation_slides(pages, ocr), list(range(1, 20)))
        ocr[1] = "Sources: P10"  # A longer ID must not satisfy P1.
        pages[2] = {"citation_labels": ["P2"]}  # Visible but unregistered.
        ocr[2] = "Sources: P2"
        self.assertEqual(visible_registered_citation_slides(pages, ocr), [1] + list(range(4, 20)))
        register[0]["location"] = ""  # An incomplete register entry is not evidence.
        self.assertEqual(visible_registered_citation_slides(pages, ocr), [1])
