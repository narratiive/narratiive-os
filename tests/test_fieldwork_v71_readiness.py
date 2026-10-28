from __future__ import annotations

import unittest

from runtime.fieldwork_v71_readiness import ACTS, audit_fieldwork_v71


def synthetic_package():
    return {
        "contract_version": "7.1.0", "artifact_id": "synthetic-only", "checksum": "synthetic-only",
        "acts": list(ACTS),
        "evidence_register": [
            {"claim_id": f"c{i}", "claim": "Synthetic hypothesis", "source": "synthetic:fixture",
             "date": "2026-10-28", "method": "fixture only", "status": "unverified", "slide": i,
             "validation_request": "Real specialist research required"}
            for i in range(1, 6)
        ],
        "opening_thesis": {key: ["c1"] for key in ("market", "brand", "audience")},
        "challenged_claim_ids": [f"c{i}" for i in range(1, 6)],
        "competitor_ad_audit": {
            "period": "synthetic", "sample": "synthetic", "method": "synthetic", "limitations": "Not real research",
            "executions": [{key: "synthetic" for key in ("brand", "asset_reference", "platform", "date", "premise", "format", "coding_rationale")}],
        },
        "commercial_prize": {
            **{key: "synthetic missing baseline" for key in ("baseline_or_missing_inputs", "timeframe", "calculation", "sensitivities", "double_counting_control")},
            "outcome_type": "missing_inputs",
            "levers": [{key: "synthetic" for key in ("lever", "marketing_mechanism", "modelled_impact", "basis")} for _ in range(4)],
        },
        "media_plan": {key: "synthetic; not an approved plan" for key in ("audience", "message", "platforms", "formats", "phasing", "paid_owned_earned", "budget_basis", "success_measures", "ninety_day_sequence")},
        "creative_direction": {**{key: "synthetic" for key in ("territory", "competitive_distinctiveness_basis", "visual_references", "execution_seeds")}, "prompts_and_slots": ["synthetic slot"]},
        "marketing_remit_only": True,
    }


class FieldworkV71ReadinessTests(unittest.TestCase):
    def test_complete_structure_never_confers_quality_or_release_approval(self):
        result = audit_fieldwork_v71(synthetic_package())
        self.assertTrue(result["structural_inputs_complete"])
        self.assertFalse(result["client_release_authorised"])
        self.assertEqual(result["source_verification"], "not_performed_by_this_audit")

    def test_legacy_package_cannot_claim_v71_from_quality_pass(self):
        result = audit_fieldwork_v71({"contract_version": "4.0.0", "quality_passed": True})
        self.assertFalse(result["structural_inputs_complete"])
        self.assertIn("wrong_contract_version", result["blockers"])
        self.assertIn("concrete_media_plan_missing", result["blockers"])

    def test_missing_model_basis_and_unverified_claim_requests_block_review(self):
        package = synthetic_package()
        del package["commercial_prize"]["double_counting_control"]
        del package["evidence_register"][0]["validation_request"]
        result = audit_fieldwork_v71(package)
        self.assertIn("commercial_model_basis_missing", result["blockers"])
        self.assertIn("unverified_claim_without_request", result["blockers"])

    def test_broken_thesis_reference_and_duplicate_challenge_do_not_pass(self):
        package = synthetic_package()
        package["opening_thesis"]["market"] = ["absent"]
        package["challenged_claim_ids"] = ["c1"] * 5
        result = audit_fieldwork_v71(package)
        self.assertIn("missing_market_thesis_evidence", result["blockers"])
        self.assertIn("five_challenged_claims_missing", result["blockers"])

    def test_malformed_optional_collections_fail_closed(self):
        package = synthetic_package()
        package["competitor_ad_audit"]["executions"] = "not a list"
        package["commercial_prize"]["levers"] = None
        result = audit_fieldwork_v71(package)
        self.assertFalse(result["structural_inputs_complete"])
