from __future__ import annotations

import unittest

from scripts.review_rendered_blueprint import rendered_copy_gaps


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
