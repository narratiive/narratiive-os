from __future__ import annotations

import unittest

from runtime.commercial_close_boundary import (
    CommercialCloseBoundary,
    CommercialCloseEvidenceError,
    CommercialClosePolicy,
)


class CommercialCloseBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = CommercialClosePolicy("loa-pass2", 500_000, 250_000)
        self.contract, self.payment = CommercialCloseBoundary.sandbox_receipts(self.policy)

    def test_sandbox_receipts_prove_flow_without_marking_live_won(self) -> None:
        result = CommercialCloseBoundary.evaluate(
            self.policy,
            self.contract,
            self.payment,
            environment="sandbox",
        )
        self.assertEqual(result["classification"], "VERIFIED SANDBOX")
        self.assertTrue(result["commercial_close_ready"])
        self.assertFalse(result["authoritative_deal_won"])
        self.assertFalse(result["onboarding_authorized"])
        self.assertFalse(result["media_activation_authorized"])

    def test_sandbox_receipts_cannot_satisfy_live_close(self) -> None:
        with self.assertRaisesRegex(CommercialCloseEvidenceError, "environment does not match"):
            CommercialCloseBoundary.evaluate(
                self.policy,
                self.contract,
                self.payment,
                environment="live",
            )

    def test_wrong_deposit_is_rejected(self) -> None:
        payment = {**self.payment, "amount_minor": 249_999}
        with self.assertRaisesRegex(CommercialCloseEvidenceError, "required deposit"):
            CommercialCloseBoundary.evaluate(
                self.policy,
                self.contract,
                payment,
                environment="sandbox",
            )

    def test_cross_opportunity_receipt_is_rejected(self) -> None:
        contract = {**self.contract, "opportunity_id": "another-client"}
        with self.assertRaisesRegex(CommercialCloseEvidenceError, "opportunity does not match"):
            CommercialCloseBoundary.evaluate(
                self.policy,
                contract,
                self.payment,
                environment="sandbox",
            )


if __name__ == "__main__":
    unittest.main()
