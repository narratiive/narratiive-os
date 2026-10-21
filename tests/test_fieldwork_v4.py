from __future__ import annotations

import unittest

from runtime.fieldwork_v4 import build_fieldwork_v4_cohort_model, validate_fieldwork_v4_opening


def cohort_input() -> dict:
    return {
        "model_type": "new_customer_cohort",
        "period": "12 months",
        "population": "new customers acquired during the period",
        "currency": "GBP",
        "inputs": [
            {"input_id": "qualified_visits", "value": 100000, "status": "client_supplied", "source_ids": ["C1"]},
            {"input_id": "first_purchase_conversion_rate", "value": 0.02, "status": "client_supplied", "source_ids": ["C1"]},
            {"input_id": "realized_revenue_per_acquired_customer", "value": 80, "status": "client_supplied", "source_ids": ["C2"]},
        ],
        "scenarios": [
            {"name": "Indexed sensitivity", "qualified_visits_multiplier": 1.1, "conversion_multiplier": 1.1, "revenue_per_customer_multiplier": 1.1, "classification": "illustrative_scenario", "assumptions": ["Equal 10% sensitivities are illustrative only."]},
        ],
        "existing_customer_revenue": {"status": "excluded_from_new_customer_cohort"},
        "limitations": ["This is not a total-company forecast."],
    }


class FieldworkV4Tests(unittest.TestCase):
    def test_indexed_sensitivity_is_33_1_percent_for_cohort_only(self) -> None:
        model = build_fieldwork_v4_cohort_model(cohort_input())
        self.assertEqual(model["baseline"]["new_customer_cohort_revenue"], 160000)
        self.assertAlmostEqual(model["scenarios"][0]["uplift_percent"], 33.1, places=6)
        self.assertEqual(model["output_metric"], "revenue")
        self.assertEqual(model["existing_customer_revenue"]["status"], "excluded_from_new_customer_cohort")

    def test_cohort_model_rejects_unlabelled_illustrative_scenario(self) -> None:
        value = cohort_input()
        value["scenarios"][0]["assumptions"] = []
        with self.assertRaisesRegex(ValueError, "require assumptions"):
            build_fieldwork_v4_cohort_model(value)

    def test_opening_fails_closed_when_any_move_is_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly five"):
            validate_fieldwork_v4_opening({"contract_version": "4.0.0", "slides": []})


if __name__ == "__main__":
    unittest.main()
