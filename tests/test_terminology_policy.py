import unittest

from runtime.terminology_policy import TerminologyPolicy


class TerminologyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TerminologyPolicy({
            "version": "1.0.0",
            "status": "active",
            "approved_terms": [
                {"term": "Growth Blueprint", "use": "Canonical strategic output"},
            ],
            "unsettled_terms": [
                {"concept": "Paid engagement", "rule": "Use descriptive language"},
            ],
            "retired_terms": [
                {"term": "Opportunity Card", "replacement": None, "rationale": "Retired"},
                {"term": "Growth Sprint", "replacement": None, "rationale": "Superseded"},
            ],
        })

    def test_detects_retired_terms_case_insensitively(self) -> None:
        violations = self.policy.scan("Create an opportunity card, then sell a GROWTH SPRINT.")
        self.assertEqual([item.term for item in violations], ["Opportunity Card", "Growth Sprint"])

    def test_does_not_match_inside_larger_words(self) -> None:
        self.assertEqual(self.policy.scan("The team is growth sprinting today."), [])

    def test_exposes_versioned_canonical_collections(self) -> None:
        self.assertEqual(self.policy.approved_terms[0]["term"], "Growth Blueprint")
        self.assertEqual(self.policy.unsettled_terms[0]["concept"], "Paid engagement")
        self.assertEqual(self.policy.retired_terms[0]["term"], "Opportunity Card")

    def test_rejects_duplicate_retired_terms(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate retired term"):
            TerminologyPolicy({
                "version": "1",
                "status": "active",
                "retired_terms": [
                    {"term": "Old Name", "rationale": "One"},
                    {"term": "old name", "rationale": "Two"},
                ],
            })

    def test_rejects_malformed_approved_terms(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires use"):
            TerminologyPolicy({
                "version": "1",
                "status": "active",
                "approved_terms": [{"term": "Growth Blueprint", "use": ""}],
                "retired_terms": [{"term": "Old Name", "rationale": "Retired"}],
            })

    def test_rejects_term_that_is_both_approved_and_retired(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cannot appear in both approved_terms and retired_terms",
        ):
            TerminologyPolicy({
                "version": "1",
                "status": "active",
                "approved_terms": [
                    {"term": "Growth Sprint", "use": "Current offer"},
                ],
                "retired_terms": [
                    {"term": " growth   sprint ", "rationale": "Superseded"},
                ],
            })

    def test_rejects_term_that_is_both_unsettled_and_retired(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cannot appear in both unsettled_terms and retired_terms",
        ):
            TerminologyPolicy({
                "version": "1",
                "status": "active",
                "unsettled_terms": [
                    {"concept": "Opportunity Card", "rule": "Do not name yet"},
                ],
                "retired_terms": [
                    {"term": "opportunity card", "rationale": "Retired"},
                ],
            })

    def test_rejects_term_that_is_both_approved_and_unsettled(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "cannot appear in both approved_terms and unsettled_terms",
        ):
            TerminologyPolicy({
                "version": "1",
                "status": "active",
                "approved_terms": [
                    {"term": "Paid Engagement", "use": "Approved offer"},
                ],
                "unsettled_terms": [
                    {"concept": "paid engagement", "rule": "Use descriptive language"},
                ],
                "retired_terms": [
                    {"term": "Old Name", "rationale": "Retired"},
                ],
            })


if __name__ == "__main__":
    unittest.main()
