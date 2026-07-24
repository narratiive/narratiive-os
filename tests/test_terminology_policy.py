import json
import tempfile
import unittest
from pathlib import Path

from runtime.terminology_policy import TerminologyPolicy


class TerminologyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TerminologyPolicy(
            {
                "version": "1.0.0",
                "status": "active",
                "approved_terms": [{"term": "Growth Blueprint"}],
                "unsettled_terms": [],
                "retired_terms": [
                    {
                        "term": "Opportunity Card",
                        "replacement": None,
                        "rationale": "Retired",
                    },
                    {
                        "term": "Growth Sprint",
                        "replacement": "approved engagement",
                        "rationale": "Superseded",
                    },
                ],
            }
        )

    def test_detects_retired_terms_case_insensitively(self) -> None:
        violations = self.policy.scan(
            "Create an opportunity card, then sell a GROWTH SPRINT."
        )
        self.assertEqual(
            [item.term for item in violations],
            ["Opportunity Card", "Growth Sprint"],
        )

    def test_does_not_match_inside_larger_words(self) -> None:
        self.assertEqual(self.policy.scan("The team is growth sprinting today."), [])

    def test_approved_terms_are_not_flagged(self) -> None:
        self.assertEqual(self.policy.scan("Produce the Growth Blueprint."), [])

    def test_require_current_explains_unapproved_replacement(self) -> None:
        with self.assertRaisesRegex(ValueError, "No replacement is approved"):
            self.policy.require_current("Send an Opportunity Card.")

    def test_rejects_duplicate_retired_terms(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate retired term"):
            TerminologyPolicy(
                {
                    "version": "1",
                    "status": "active",
                    "retired_terms": [
                        {"term": "Old Name", "rationale": "One"},
                        {"term": "old name", "rationale": "Two"},
                    ],
                }
            )

    def test_loads_policy_from_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "terminology.json"
            path.write_text(
                json.dumps(
                    {
                        "version": "1",
                        "status": "active",
                        "retired_terms": [
                            {"term": "Old Name", "rationale": "Retired"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            loaded = TerminologyPolicy.from_path(path)
            self.assertEqual(loaded.version, "1")


if __name__ == "__main__":
    unittest.main()
