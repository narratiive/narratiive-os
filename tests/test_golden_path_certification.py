from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_golden_path_certification import run


class GoldenPathCertificationTests(unittest.TestCase):
    def test_fresh_isolated_certification_reaches_exact_version_blueprint_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run(Path(tmp) / "certification")
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["certification_id"].startswith("golden-path-"))
            self.assertTrue(report["artifact_governance_complete"])
            self.assertTrue(all(report["acceptance_proofs"].values()))
        self.assertEqual(report["quality_revision"]["final_version"], 2)
        self.assertTrue(report["duplicate_execution_suppressed"])
        self.assertTrue(report["restart_resume_preserved_token"])
        self.assertFalse(report["external_action_taken"])
        self.assertEqual(report["false_success_events"], [])
        self.assertEqual(report["missing_workflows"], [])


if __name__ == "__main__":
    unittest.main()
