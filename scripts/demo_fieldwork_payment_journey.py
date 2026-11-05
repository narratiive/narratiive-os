#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.fieldwork_payments import (
    ApprovedFieldworkProposal,
    FieldworkPaymentService,
    FieldworkPaymentStore,
    stripe_signature,
)


class DemoStripe:
    def create_checkout(self, payload, *, idempotency_key):
        return {"id": "cs_test_demo", "url": "https://checkout.stripe.test/c/pay/fieldwork-demo", "status": "open", "payment_status": "unpaid"}

    def retrieve_checkout(self, session_id):
        raise AssertionError("reconciliation is not needed in the happy-path demo")


def main() -> int:
    now = 1_800_000_000
    webhook_secret = "whsec_test_demo"
    stages: list[dict[str, object]] = []

    def action(name: str):
        def run(_context):
            receipt = {"verified": True, "status": "verified", "receipt_id": f"test-{name}-receipt"}
            stages.append({"stage": name, **receipt})
            return receipt
        return run

    def verify(context):
        item = context["proposal"]
        return {
            "verified": True,
            "proposal_id": item["proposal_id"],
            "proposal_checksum": item["proposal_checksum"],
            "founder_approval_id": item["founder_approval_id"],
        }

    with tempfile.TemporaryDirectory() as temporary:
        service = FieldworkPaymentService(
            FieldworkPaymentStore(Path(temporary)),
            DemoStripe(),
            webhook_secret=webhook_secret,
            success_url="https://example.invalid/success",
            cancel_url="https://example.invalid/cancel",
            crm_update=action("crm_update"),
            founder_notification=action("tony_telegram_notification"),
            workflow_authorisation=action("fieldwork_authorised_and_existing_workflow_initiated"),
            client_confirmation=action("client_confirmation_and_invoice_notice"),
            proposal_verifier=verify,
            clock=lambda: now,
        )
        proposal = ApprovedFieldworkProposal(
            proposal_id="proposal-demo-001", workspace_id="narratiive", client_id="client-demo-001",
            client_name="Synthetic FIELDWORK Client", client_contact_name="Alex", client_email="client@example.invalid",
            proposal_url="https://drive.example.invalid/proposal-demo-001", proposal_checksum="sha256:demo",
            scope_summary="Synthetic approved FIELDWORK scope.", total_amount_minor=600_000,
            deposit_amount_minor=300_000, currency="GBP", balance_terms="Balance due on agreed delivery.",
            service_terms_url="https://narratiive.example.invalid/terms", founder_approval_id="approval-demo-001",
            founder_approved_at="2026-10-30T09:00:00+00:00", parent_workflow_run_id="proposal-run-demo-001",
            commercial_record_id="notion-demo-001", required_inputs=("approved brief",), received_inputs=("approved brief",),
            workflow_inputs={"approved_growth_sprint_scope": {"scope": "synthetic"}},
        )
        checkout = service.create_checkout(proposal)
        stages.append({"stage": "approved_proposal_checkout_created", "verified": True, "session_id": checkout["checkout"]["session_id"]})
        session = {
            "id": "cs_test_demo", "mode": "payment", "payment_status": "paid", "amount_total": 300_000,
            "currency": "gbp", "client_reference_id": "client-demo-001", "payment_intent": "pi_test_demo",
            "invoice": "in_test_demo", "consent": {"terms_of_service": "accepted"},
            "metadata": {"proposal_id": "proposal-demo-001", "workspace_id": "narratiive", "client_id": "client-demo-001", "proposal_checksum": "sha256:demo"},
        }
        event = {"id": "evt_test_demo", "type": "checkout.session.completed", "livemode": False, "data": {"object": session}}
        raw = json.dumps(event, separators=(",", ":")).encode()
        result = service.handle_webhook(raw, stripe_signature(raw, webhook_secret, now))
        stages.insert(1, {"stage": "deposit_and_webhook_verified", "verified": True, "event_id": result["event_id"], "payment_intent": result["payment"]["payment_intent"]})
        print(json.dumps({"mode": "stripe_test", "work_authorised": result["work_authorised"], "journey": stages}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
