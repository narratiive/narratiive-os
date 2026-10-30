#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from wsgiref.simple_server import make_server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.fieldwork_payment_bridge import FieldworkPaymentApplication
from runtime.fieldwork_payments import (
    ApprovedFieldworkProposal,
    FieldworkPaymentService,
    FieldworkPaymentStore,
    StripeApiClient,
)


def main() -> int:
    proposal_path = Path(_required("FIELDWORK_APPROVED_PROPOSALS_PATH")).expanduser().resolve()
    if not proposal_path.is_file():
        raise RuntimeError("FIELDWORK_APPROVED_PROPOSALS_PATH must be an existing file")
    if stat.S_IMODE(proposal_path.stat().st_mode) & 0o077:
        raise RuntimeError("approved proposal registry must use mode 0600")
    runtime_root = Path(os.getenv("FIELDWORK_PAYMENT_RUNTIME_ROOT", ".runtime/fieldwork-payments")).expanduser().resolve()
    stripe = StripeApiClient(_required("STRIPE_SECRET_KEY"))
    service = FieldworkPaymentService(
        FieldworkPaymentStore(runtime_root),
        stripe,
        webhook_secret=_required("STRIPE_WEBHOOK_SECRET"),
        success_url=_required("FIELDWORK_CHECKOUT_SUCCESS_URL"),
        cancel_url=_required("FIELDWORK_CHECKOUT_CANCEL_URL"),
    )

    def load_proposal(proposal_id: str) -> ApprovedFieldworkProposal:
        try:
            value = json.loads(proposal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("approved proposal registry is unreadable") from exc
        proposals = value.get("proposals") if isinstance(value, dict) else None
        raw = proposals.get(proposal_id) if isinstance(proposals, dict) else None
        if not isinstance(raw, dict):
            raise ValueError("approved proposal is not registered")
        return ApprovedFieldworkProposal(**raw)

    app = FieldworkPaymentApplication(
        service,
        bridge_token=_required("FIELDWORK_PAYMENT_BRIDGE_TOKEN"),
        proposal_loader=load_proposal,
    )
    host = os.getenv("FIELDWORK_PAYMENT_HOST", "127.0.0.1")
    port = int(os.getenv("FIELDWORK_PAYMENT_PORT", "8794"))
    with make_server(host, port, app) as server:
        print(f"FIELDWORK Stripe test bridge listening on {host}:{port}")
        server.serve_forever()
    return 0


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
