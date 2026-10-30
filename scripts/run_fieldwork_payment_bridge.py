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
from runtime.fieldwork_payment_integrations import verify_approved_proposal
from runtime.fieldwork_payment_integrations import (
    notion_payment_recorder,
    telegram_founder_notifier,
    tony_workflow_authoriser,
)
from runtime.tony_dispatch_adapters import build_http_dispatchers
from openclaw.telegram_outbound import TelegramConfig, TelegramSender


def main() -> int:
    proposal_path = Path(_required("FIELDWORK_APPROVED_PROPOSALS_PATH")).expanduser().resolve()
    if not proposal_path.is_file():
        raise RuntimeError("FIELDWORK_APPROVED_PROPOSALS_PATH must be an existing file")
    if stat.S_IMODE(proposal_path.stat().st_mode) & 0o077:
        raise RuntimeError("approved proposal registry must use mode 0600")
    runtime_root = Path(os.getenv("FIELDWORK_PAYMENT_RUNTIME_ROOT", ".runtime/fieldwork-payments")).expanduser().resolve()
    workflow_root = Path(_required("FIELDWORK_WORKFLOW_RUNTIME_ROOT")).expanduser().resolve()
    workspace_id = _required("FIELDWORK_WORKSPACE_ID")
    stripe = StripeApiClient(_required("STRIPE_SECRET_KEY"))
    actions = _downstream_actions(workflow_root, workspace_id, os.environ)
    service = FieldworkPaymentService(
        FieldworkPaymentStore(runtime_root),
        stripe,
        webhook_secret=_required("STRIPE_WEBHOOK_SECRET"),
        success_url=_required("FIELDWORK_CHECKOUT_SUCCESS_URL"),
        cancel_url=_required("FIELDWORK_CHECKOUT_CANCEL_URL"),
        proposal_verifier=verify_approved_proposal(workflow_root, workspace_id=workspace_id),
        **actions,
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


def _downstream_actions(workflow_root: Path, workspace_id: str, environ) -> dict:
    """Wire only explicitly isolated sandbox effects for a test-mode bridge."""

    if str(environ.get("FIELDWORK_PAYMENT_DOWNSTREAM_MODE") or "").strip() != "sandbox_isolated":
        raise RuntimeError("FIELDWORK payment bridge requires FIELDWORK_PAYMENT_DOWNSTREAM_MODE=sandbox_isolated")
    allowed_proposals = {
        item.strip() for item in str(environ.get("FIELDWORK_PAYMENT_SANDBOX_PROPOSAL_IDS") or "").split(",")
        if item.strip()
    }
    test_recipient = str(environ.get("FIELDWORK_PAYMENT_SANDBOX_TEST_RECIPIENT") or "").strip().casefold()
    if not allowed_proposals or not test_recipient or "@" not in test_recipient:
        raise RuntimeError("sandbox downstream actions require explicit proposal IDs and a test recipient")

    def sandbox_only(action):
        def guarded(context):
            proposal = context.get("proposal") if isinstance(context, dict) else None
            if not isinstance(proposal, dict):
                raise RuntimeError("sandbox downstream action lacks proposal evidence")
            if str(proposal.get("proposal_id") or "").strip() not in allowed_proposals:
                raise RuntimeError("sandbox downstream action rejected an unapproved proposal")
            if str(proposal.get("client_email") or "").strip().casefold() != test_recipient:
                raise RuntimeError("sandbox downstream action rejected a non-test recipient")
            return action(context)
        return guarded

    dispatchers = build_http_dispatchers(environ)
    notion = dispatchers.get("Notion")
    if notion is None:
        raise RuntimeError("FIELDWORK payment bridge requires the configured Notion dispatcher")
    actions = {
        "crm_update": sandbox_only(notion_payment_recorder(notion)),
        "workflow_authorisation": sandbox_only(
            tony_workflow_authoriser(
                workflow_root,
                workspace_id=workspace_id,
                dispatchers=dispatchers,
                environ=environ,
            )
        ),
    }
    if str(environ.get("TONY_TELEGRAM_BOT_TOKEN") or "").strip() and str(environ.get("TONY_TELEGRAM_CHAT_ID") or "").strip():
        sandbox_chat_id = str(environ.get("FIELDWORK_PAYMENT_SANDBOX_TELEGRAM_CHAT_ID") or "").strip()
        if sandbox_chat_id != str(environ["TONY_TELEGRAM_CHAT_ID"]).strip():
            raise RuntimeError("sandbox Telegram routing must use the explicitly configured internal test chat")
        actions["founder_notification"] = telegram_founder_notifier(
            TelegramSender(TelegramConfig.from_env(environ)),
            sandbox_chat_id,
        )
        actions["founder_notification"] = sandbox_only(actions["founder_notification"])
    # A Stripe payment never creates a client-facing send without a separate
    # exact delivery approval, so client_confirmation is deliberately omitted.
    return actions


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
