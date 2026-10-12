from __future__ import annotations

import unittest

from runtime.senior_strategist_review_worker import SeniorStrategistReviewWorker
from tests.test_workflow_quality import blueprint_director_output, growth_blueprint_output


class SeniorStrategistReviewWorkerTests(unittest.TestCase):
    def contract(self) -> dict:
        governed = growth_blueprint_output()
        directed = blueprint_director_output(client_name="Synthetic Client", page_count=17)
        governed.update(directed)
        governed["blueprint_director_output_identity"] = {"checksum": "a" * 64}
        governed["client_context"] = {"brand_name": "Synthetic Client"}
        governed["approved_strategy_thesis"] = {
            "thesis_statement": "Synthetic Client should make proof easier to use at the moment of choice."
        }
        return governed

    def test_accepts_trace_refs_from_governed_evidence_and_exact_thesis_fields(self) -> None:
        contract = self.contract()
        contract["editorial_trace"][0]["evidence_refs"] = ["ev-1", "thesis:thesis_statement"]
        result = SeniorStrategistReviewWorker()(contract)
        self.assertTrue(result["senior_strategist_review"]["evidence_support"]["passed"])
        self.assertEqual(result["review_disposition"], "forward")

    def test_rejects_untraceable_editorial_evidence_reference(self) -> None:
        contract = self.contract()
        contract["editorial_trace"][0]["evidence_refs"] = ["invented:source"]
        result = SeniorStrategistReviewWorker()(contract)
        self.assertFalse(result["senior_strategist_review"]["evidence_support"]["passed"])
        self.assertEqual(result["review_disposition"], "revise")
        self.assertTrue(result["actionable_findings"])


if __name__ == "__main__":
    unittest.main()
