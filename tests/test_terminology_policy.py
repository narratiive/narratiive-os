import unittest

from runtime.terminology_policy import TerminologyPolicy


class TerminologyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TerminologyPolicy({
            "version": "1.0.0",
            "status": "active",
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


if __name__ == "__main__":
    unittest.main()
