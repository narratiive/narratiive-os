import tempfile
import unittest
from pathlib import Path

from runtime.repository_terminology_audit import audit_repository
from runtime.terminology_policy import TerminologyPolicy


class RepositoryTerminologyAuditTests(unittest.TestCase):
    @staticmethod
    def policy() -> TerminologyPolicy:
        return TerminologyPolicy(
            {
                "status": "active",
                "version": "1.0.0",
                "version_note": "Test policy.",
                "approved_terms": [
                    {"term": "Growth Blueprint", "use": "Canonical strategic output."}
                ],
                "unsettled_terms": [],
                "retired_terms": [
                    {
                        "term": "Growth Sprint",
                        "replacement": None,
                        "rationale": "Retired commercial engagement label.",
                    },
                    {
                        "term": "Opportunity Card",
                        "replacement": "personalised prospecting asset",
                        "rationale": "Retired prospecting label.",
                    },
                ],
            }
        )

    def test_reports_retired_terms_with_deterministic_locations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime").mkdir()
            (root / "runtime" / "brief.py").write_text(
                "title = 'Growth Blueprint'\nlabel = 'Growth Sprint'\n",
                encoding="utf-8",
            )
            (root / "scripts").mkdir()
            (root / "scripts" / "outreach.py").write_text(
                "message = 'Create an Opportunity Card.'\n",
                encoding="utf-8",
            )

            findings = audit_repository(root, policy=self.policy())

        self.assertEqual(
            [(item.path, item.line, item.column, item.term) for item in findings],
            [
                ("runtime/brief.py", 2, 10, "Growth Sprint"),
                ("scripts/outreach.py", 1, 22, "Opportunity Card"),
            ],
        )
        self.assertEqual(findings[1].replacement, "personalised prospecting asset")

    def test_ignores_non_runtime_history_and_test_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("docs", "knowledge/proposition", "tests"):
                (root / relative).mkdir(parents=True)
                (root / relative / "history.md").write_text(
                    "Growth Sprint and Opportunity Card",
                    encoding="utf-8",
                )

            findings = audit_repository(root, policy=self.policy())

        self.assertEqual(findings, ())

    def test_missing_audited_roots_fail_closed_without_inventing_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            findings = audit_repository(directory, policy=self.policy())

        self.assertEqual(findings, ())


if __name__ == "__main__":
    unittest.main()
