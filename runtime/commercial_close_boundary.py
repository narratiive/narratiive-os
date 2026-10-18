from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


class CommercialCloseEvidenceError(ValueError):
    """Raised when contract or payment evidence crosses the wrong boundary."""


@dataclass(frozen=True, slots=True)
class CommercialClosePolicy:
    opportunity_id: str
    total_amount_minor: int
    deposit_amount_minor: int
    currency: str = "GBP"


class CommercialCloseBoundary:
    """Validate commercial-close receipts without confusing sandbox with live money.

    Sandbox receipts prove the orchestration and acceptance gates only. They can
    never mark a live opportunity Won, start onboarding, release client work, or
    authorise media activation.
    """

    CONTRACT_EVENT = "contract.executed"
    PAYMENT_EVENT = "payment.succeeded"
    SANDBOX_CONTRACT_PROVIDER = "narratiive_contract_sandbox"
    SANDBOX_PAYMENT_PROVIDER = "narratiive_payment_sandbox"

    @classmethod
    def sandbox_receipts(
        cls,
        policy: CommercialClosePolicy,
        *,
        occurred_at: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(
            f"sandbox\0{policy.opportunity_id}\0{policy.deposit_amount_minor}\0{policy.currency}".encode()
        ).hexdigest()[:24]
        common = {
            "environment": "sandbox",
            "opportunity_id": policy.opportunity_id,
            "occurred_at": timestamp,
            "verified": True,
            "simulated": True,
        }
        return (
            {
                **common,
                "provider": cls.SANDBOX_CONTRACT_PROVIDER,
                "event_id": f"sandbox-contract-{digest}",
                "event_type": cls.CONTRACT_EVENT,
                "contract_version": "FIELDWORK-5000-50-50-v1",
            },
            {
                **common,
                "provider": cls.SANDBOX_PAYMENT_PROVIDER,
                "event_id": f"sandbox-payment-{digest}",
                "event_type": cls.PAYMENT_EVENT,
                "amount_minor": policy.deposit_amount_minor,
                "currency": policy.currency,
            },
        )

    @classmethod
    def evaluate(
        cls,
        policy: CommercialClosePolicy,
        contract: Mapping[str, Any],
        payment: Mapping[str, Any],
        *,
        environment: str,
    ) -> dict[str, Any]:
        requested = environment.strip().casefold()
        if requested not in {"sandbox", "live"}:
            raise CommercialCloseEvidenceError("commercial environment must be sandbox or live")
        cls._require_receipt(contract, policy, cls.CONTRACT_EVENT, requested)
        cls._require_receipt(payment, policy, cls.PAYMENT_EVENT, requested)
        try:
            amount = int(payment.get("amount_minor"))
        except (TypeError, ValueError) as exc:
            raise CommercialCloseEvidenceError("payment receipt amount is invalid") from exc
        if amount != policy.deposit_amount_minor:
            raise CommercialCloseEvidenceError("payment receipt does not match the required deposit")
        if str(payment.get("currency") or "").upper() != policy.currency.upper():
            raise CommercialCloseEvidenceError("payment receipt currency does not match the policy")

        if requested == "sandbox":
            if contract.get("provider") != cls.SANDBOX_CONTRACT_PROVIDER:
                raise CommercialCloseEvidenceError("sandbox contract receipt used an unrecognised provider")
            if payment.get("provider") != cls.SANDBOX_PAYMENT_PROVIDER:
                raise CommercialCloseEvidenceError("sandbox payment receipt used an unrecognised provider")
            classification = "VERIFIED SANDBOX"
        else:
            for receipt in (contract, payment):
                if receipt.get("simulated") is True or "sandbox" in str(receipt.get("provider") or "").casefold():
                    raise CommercialCloseEvidenceError("sandbox evidence cannot satisfy a live commercial close")
            classification = "VERIFIED LIVE"

        return {
            "classification": classification,
            "environment": requested,
            "opportunity_id": policy.opportunity_id,
            "contract_event_id": str(contract.get("event_id") or ""),
            "payment_event_id": str(payment.get("event_id") or ""),
            "deposit_amount_minor": amount,
            "currency": policy.currency,
            "commercial_close_ready": True,
            "authoritative_deal_won": requested == "live",
            "onboarding_authorized": False,
            "client_delivery_authorized": False,
            "media_activation_authorized": False,
    }
    @staticmethod
    def _require_receipt(
        receipt: Mapping[str, Any],
        policy: CommercialClosePolicy,
        event_type: str,
        environment: str,
    ) -> None:
        if receipt.get("verified") is not True:
            raise CommercialCloseEvidenceError(f"{event_type} receipt is not verified")
        if str(receipt.get("environment") or "").casefold() != environment:
            raise CommercialCloseEvidenceError(f"{event_type} receipt environment does not match")
        if str(receipt.get("event_type") or "") != event_type:
            raise CommercialCloseEvidenceError(f"expected {event_type} receipt")
        if str(receipt.get("opportunity_id") or "") != policy.opportunity_id:
            raise CommercialCloseEvidenceError(f"{event_type} receipt opportunity does not match")
        if not str(receipt.get("event_id") or "").strip():
            raise CommercialCloseEvidenceError(f"{event_type} receipt has no event identifier")
