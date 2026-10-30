from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any, Callable, Mapping

from runtime.fieldwork_payments import FieldworkPaymentError
from runtime.tony_internal_review_delivery import fieldwork_commercial_offer_digest


def notion_payment_recorder(notion_dispatcher: Callable[[dict[str, Any]], Mapping[str, Any]]):
    """Project verified payment into the existing canonical commercial record."""

    def record(context: Mapping[str, Any]) -> Mapping[str, Any]:
        proposal = _mapping(context.get("proposal"))
        payment = _mapping(context.get("payment"))
        record_id = _text(proposal.get("commercial_record_id"))
        proposal_id = _text(proposal.get("proposal_id"))
        payment_intent = _text(payment.get("payment_intent"))
        if not record_id or not proposal_id or not payment_intent:
            raise FieldworkPaymentError("canonical commercial identity is incomplete")
        key = hashlib.sha256(f"{proposal_id}:{payment_intent}".encode("utf-8")).hexdigest()
        outstanding = [str(item) for item in proposal.get("outstanding_inputs", []) if str(item).strip()]
        next_action = (
            "Collect the remaining FIELDWORK inputs before authorising specialist execution: " + ", ".join(outstanding)
            if outstanding
            else "Begin the authorised FIELDWORK workflow through Tony's existing orchestration."
        )
        result = notion_dispatcher(
            {
                "worker": "Notion",
                "execution_mode": "approved_write",
                "approval_granted": True,
                "approval_scope": "verified_fieldwork_acceptance_and_payment_projection",
                "idempotency_key": key,
                "target": {"record_id": record_id, "client_id": proposal.get("client_id", ""), "area": "commercial"},
                "payload": {
                    "kind": "fieldwork_verified_acceptance_payment",
                    "projection_key": key,
                    "proposal_id": proposal_id,
                    "payment_intent": payment_intent,
                    "stripe_event_id": payment.get("stripe_event_id", ""),
                    "recommended_next_action": next_action,
                },
                "instruction": "Record the exact verified FIELDWORK proposal acceptance and deposit against the existing canonical commercial record. Preserve the payment evidence marker and do not create a second client record.",
                "expected_evidence": "verified Notion update of the exact commercial record",
                "return_to": "FIELDWORK payment boundary",
                "execution_truth": "not_dispatched",
            }
        )
        return dict(result)

    return record


def tony_workflow_authoriser(
    workflow_root: Path,
    *,
    workspace_id: str,
    dispatchers: Mapping[str, Callable] | None = None,
    environ: Mapping[str, str] | None = None,
):
    """Commission the existing downstream workflow; never create a parallel engine."""

    def authorise(context: Mapping[str, Any]) -> Mapping[str, Any]:
        from runtime.tony_workflow_commands import FileWorkflowCommandBackend

        proposal = _mapping(context.get("proposal"))
        payment = _mapping(context.get("payment"))
        verification = verify_approved_proposal(workflow_root, workspace_id=workspace_id)(context)
        parent_run_id = _text(proposal.get("parent_workflow_run_id"))
        target_workflow_id = _text(proposal.get("target_workflow_id"))
        client_id = _text(proposal.get("client_id"))
        if not parent_run_id or not target_workflow_id or not client_id:
            raise FieldworkPaymentError("workflow authorisation identity is incomplete")
        backend = FileWorkflowCommandBackend(
            workflow_root,
            dispatchers=dispatchers,
            environ=environ,
            workspace_id=workspace_id,
        )
        parent = _approved_parent_workflow(backend, proposal, workspace_id)
        inputs = dict(_mapping(proposal.get("workflow_inputs")))
        inputs["verified_acceptance"] = dict(_mapping(context.get("acceptance")))
        inputs["verified_payment"] = dict(payment)
        commissioned, replay = backend.commission(
            parent,
            target_workflow_id=target_workflow_id,
            inputs=inputs,
            commitment_id=f"fieldwork-payment:{proposal.get('proposal_id')}:{payment.get('payment_intent')}",
        )
        return {
            "verified": True,
            "status": "duplicate_suppressed" if replay else "commissioned",
            "commissioned": True,
            "replay": replay,
            "run_id": commissioned.run_id,
            "workflow_id": commissioned.workflow_id,
            "workspace_id": commissioned.workspace_id,
            "client_id": commissioned.client_id,
        }

    return authorise


def verify_approved_proposal(workflow_root: Path, *, workspace_id: str, dispatchers: Mapping[str, Callable] | None = None, environ: Mapping[str, str] | None = None):
    """Prove the registry entry is the exact approved workflow artefact before Checkout."""
    def verify(context: Mapping[str, Any]) -> Mapping[str, Any]:
        from runtime.tony_workflow_commands import FileWorkflowCommandBackend
        proposal = _mapping(context.get("proposal"))
        backend = FileWorkflowCommandBackend(workflow_root, dispatchers=dispatchers, environ=environ, workspace_id=workspace_id)
        parent = _approved_parent_workflow(backend, proposal, workspace_id)
        return {
            "verified": True,
            "proposal_id": _text(proposal.get("proposal_id")),
            "proposal_checksum": _text(proposal.get("proposal_checksum")),
            "founder_approval_id": _text(proposal.get("founder_approval_id")),
            "parent_run_id": parent.run_id,
        }
    return verify


def _approved_parent_workflow(backend: Any, proposal: Mapping[str, Any], workspace_id: str):
    parent_run_id = _text(proposal.get("parent_workflow_run_id"))
    client_id = _text(proposal.get("client_id"))
    matches = [state for state in backend.list_states() if state.run_id == parent_run_id and state.client_id == client_id and state.workspace_id == workspace_id]
    if len(matches) != 1:
        raise FieldworkPaymentError("exact approved parent workflow run was not found")
    parent = matches[0]
    if parent.approval_status != "approved" or not parent.approval_history or not parent.stages:
        raise FieldworkPaymentError("parent proposal workflow lacks recorded human approval")
    approval = parent.approval_history[-1]
    binding = approval.get("approval_binding") if isinstance(approval, Mapping) else None
    if not isinstance(binding, Mapping):
        raise FieldworkPaymentError("parent proposal workflow lacks an exact approval binding")
    offer = binding.get("fieldwork_commercial_offer")
    approval_record_id = _text(approval.get("approval_record_id"))
    if not isinstance(offer, Mapping) or not approval_record_id or _text(binding.get("approval_record_id")) != approval_record_id:
        raise FieldworkPaymentError("parent proposal workflow lacks a complete canonical commercial approval")
    approval_token = _text(binding.get("approval_binding_digest"))
    expected_offer_digest = fieldwork_commercial_offer_digest(approval_token, offer)
    if not approval_token or not hmac.compare_digest(
        _text(binding.get("fieldwork_commercial_offer_digest")), expected_offer_digest
    ):
        raise FieldworkPaymentError("canonical commercial offer digest is missing or has been tampered with")
    if _text(proposal.get("founder_approval_id")) != approval_record_id:
        raise FieldworkPaymentError("founder approval does not match the exact approved commercial offer")
    if _text(proposal.get("founder_approved_at")) != _text(approval.get("approved_at")):
        raise FieldworkPaymentError("founder approval timestamp does not match workflow evidence")
    artifacts = [artifact for stage in parent.stages for artifact in stage.output_artifacts]
    artifact = artifacts[-1] if artifacts else None
    artifact_checksum = _text(artifact.checksum if artifact else "").removeprefix("sha256:")
    proposal_checksum = _text(proposal.get("proposal_checksum")).removeprefix("sha256:")
    if not artifact_checksum or artifact_checksum != proposal_checksum:
        raise FieldworkPaymentError("proposal checksum does not match the approved workflow artefact")
    expected_version = _text(getattr(artifact, "metadata", {}).get("version") if artifact else "") or f"v{parent.stages[-1].revision_count + 1}"
    if (
        _text(binding.get("workflow_id")) != _text(getattr(parent, "workflow_id", ""))
        or _text(binding.get("run_id")) != parent.run_id
        or _text(binding.get("artifact_id")) != _text(getattr(artifact, "artifact_id", ""))
        or _text(binding.get("artifact_checksum")).removeprefix("sha256:") != artifact_checksum
        or _text(binding.get("artifact_version")) != expected_version
    ):
        raise FieldworkPaymentError("founder approval binding does not match the exact workflow artefact")
    if (
        _text(offer.get("canonical_workspace_id")) != workspace_id
        or _text(offer.get("canonical_client_id")) != client_id
        or _text(offer.get("proposal_id")) != _text(proposal.get("proposal_id"))
        or _text(offer.get("recipient_email")).casefold() != _text(proposal.get("client_email")).casefold()
        or _text(offer.get("proposal_url")) != _text(proposal.get("proposal_url"))
        or _text(offer.get("scope_summary")) != _text(proposal.get("scope_summary"))
        or _text(offer.get("balance_terms")) != _text(proposal.get("balance_terms"))
        or _text(offer.get("service_terms_url")) != _text(proposal.get("service_terms_url"))
        or _text(offer.get("proposal_artifact_id")) != _text(getattr(artifact, "artifact_id", ""))
        or _text(offer.get("proposal_artifact_version")) != expected_version
        or _text(offer.get("proposal_artifact_checksum")).removeprefix("sha256:") != artifact_checksum
        or offer.get("fixed_investment_minor") != proposal.get("total_amount_minor")
        or offer.get("deposit_amount_minor") != proposal.get("deposit_amount_minor")
        or _text(offer.get("currency")).casefold() != _text(proposal.get("currency")).casefold()
    ):
        raise FieldworkPaymentError("founder commercial approval does not match the requested proposal, recipient, artefact or terms")
    return parent


def telegram_founder_notifier(sender: Any, chat_id: str):
    def notify(context: Mapping[str, Any]) -> Mapping[str, Any]:
        proposal = _mapping(context.get("proposal"))
        payment = _mapping(context.get("payment"))
        outstanding = [str(item) for item in proposal.get("outstanding_inputs", []) if str(item).strip()]
        readiness = (
            "FIELDWORK is paid and ready for Tony to commission."
            if not outstanding
            else "Payment is verified; execution remains blocked until these inputs arrive: " + ", ".join(outstanding) + "."
        )
        receipt = sender.send(
            chat_id,
            f"FIELDWORK accepted and deposit verified for {proposal.get('client_name')}. "
            f"Proposal {proposal.get('proposal_id')}; Stripe payment {payment.get('payment_intent')}. {readiness}",
        )
        return {"verified": bool(receipt.get("message_id")), "status": "verified", **dict(receipt)}

    return notify


def gmail_client_confirmation(gmail_dispatcher: Callable[[dict[str, Any]], Mapping[str, Any]]):
    def send(context: Mapping[str, Any]) -> Mapping[str, Any]:
        proposal = _mapping(context.get("proposal"))
        payment = _mapping(context.get("payment"))
        outstanding = [str(item) for item in context.get("outstanding_inputs", []) if str(item).strip()]
        clock_started = context.get("delivery_clock_started") is True
        if clock_started:
            timing = "All starting conditions are satisfied, so your seven-day FIELDWORK delivery window is now under way."
        else:
            timing = (
                "Your deposit is confirmed. The seven-day delivery window will begin only when we have verified: "
                + ", ".join(outstanding)
                + "."
            )
        invoice = _text(context.get("invoice_id"))
        receipt_note = f" Stripe has issued invoice {invoice}." if invoice else " Stripe receipt/invoice issuance is being reconciled; we will not claim it is issued until Stripe confirms it."
        key = hashlib.sha256(
            f"fieldwork-confirmation:{proposal.get('proposal_id')}:{payment.get('payment_intent')}".encode("utf-8")
        ).hexdigest()
        result = gmail_dispatcher(
            {
                "worker": "Gmail",
                "execution_mode": "approved_write",
                "approval_granted": True,
                "approval_scope": "verified_fieldwork_payment_confirmation",
                "idempotency_key": key,
                "target": {"recipient_email": proposal.get("client_email", ""), "client_id": proposal.get("client_id", "")},
                "payload": {
                    "kind": "fieldwork_payment_confirmation",
                    "recipient_email": proposal.get("client_email", ""),
                    "subject": f"FIELDWORK confirmed — {proposal.get('client_name')}",
                    "body": (
                        "Hello,\n\nThank you — we have securely verified your FIELDWORK proposal acceptance and deposit."
                        + receipt_note
                        + "\n\n"
                        + timing
                        + "\n\nWe will keep you clear on progress and any input needed from you.\n\nNarratiive"
                    ),
                },
                "instruction": "Send the exact post-payment confirmation. Do not promise a calendar delivery date unless the recorded prerequisites have started the seven-day window.",
                "expected_evidence": "verified Gmail send with message identifier",
                "return_to": "FIELDWORK payment boundary",
                "execution_truth": "not_dispatched",
            }
        )
        return dict(result)

    return send


def gmail_proposal_delivery(gmail_dispatcher: Callable[[dict[str, Any]], Mapping[str, Any]], proposal_verifier: Action):
    """Use only after the exact proposal and client send have founder approval."""

    def send(proposal, *, checkout_url: str) -> Mapping[str, Any]:
        from runtime.fieldwork_payments import FieldworkPaymentService
        verified = proposal_verifier({"proposal": FieldworkPaymentService._proposal_record(proposal)})
        if verified.get("verified") is not True:
            raise FieldworkPaymentError("proposal delivery lacks exact founder approval evidence")
        if _text(verified.get("proposal_id")) != _text(getattr(proposal, "proposal_id", "")) or _text(verified.get("proposal_checksum")) != _text(getattr(proposal, "proposal_checksum", "")):
            raise FieldworkPaymentError("proposal delivery approval does not bind the exact proposal")
        email = FieldworkPaymentService._proposal_email(proposal, checkout_url)
        key = hashlib.sha256(f"fieldwork-proposal:{proposal.proposal_id}:{proposal.founder_approval_id}".encode("utf-8")).hexdigest()
        return gmail_dispatcher(
            {
                "worker": "Gmail",
                "execution_mode": "approval_gated_write",
                "approval_granted": True,
                "approval_scope": "founder_approved_fieldwork_proposal_send",
                "idempotency_key": key,
                "target": {"recipient_email": email["recipient"]},
                "payload": {
                    "kind": "fieldwork_proposal_delivery",
                    "recipient_email": email["recipient"],
                    "subject": email["subject"],
                    "body": email["body"],
                    "html_body": email["html_body"],
                },
                "instruction": "Send the exact founder-approved FIELDWORK proposal email with its approved proposal and Stripe Checkout links. Do not alter commercial terms.",
                "expected_evidence": "verified Gmail send with message identifier",
                "return_to": "FIELDWORK payment boundary",
                "execution_truth": "not_dispatched",
            }
        )

    return send


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
