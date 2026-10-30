from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import quote
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from runtime.models import ArtifactRef, WorkflowState, WorkflowStatus
from runtime.human_review_artifacts import (
    HumanReviewArtifact,
    HumanReviewArtifactStore,
    HumanReviewPresentationService,
)


INTERNAL_REVIEW_ADDRESS = "hello@narratiive.com"
INTERNAL_REVIEW_APPROVAL_SCOPE = "narratiive_internal_artifact_review"
FIELDWORK_PROPOSAL_WORKFLOW_ID = "discovery_evidence_to_growth_sprint_proposal"

SUBSTANTIAL_ARTIFACT_TYPES = frozenset(
    {
        "blueprint_lite",
        "discovery_synthesis",
        "growth_sprint_proposal",
        "strategy_thesis",
        "growth_blueprint",
        "campaign_world",
        "creative_directors_bible",
        "research_report",
    }
)


class InternalReviewDeliveryError(ValueError):
    pass


def workflow_approval_token(state: WorkflowState) -> str | None:
    """Bind one approval decision to the current run, gate and artefact version."""

    if state.status is not WorkflowStatus.AWAITING_APPROVAL or state.approval_status != "pending":
        return None
    artifact = latest_artifact(state)
    if artifact is None:
        return None
    material = "\0".join(
        (
            state.workspace_id,
            state.client_id,
            state.workflow_id,
            state.run_id,
            state.current_stage_id or "",
            state.proposed_next_action or "",
            artifact.artifact_id,
            artifact.checksum or "",
            _artifact_version(artifact),
            str(artifact.metadata.get("reviewed_artifact_id") or ""),
            str(artifact.metadata.get("reviewed_artifact_checksum") or ""),
            str(artifact.metadata.get("reviewed_artifact_version") or ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def latest_artifact(state: WorkflowState) -> ArtifactRef | None:
    return next(
        (stage.output_artifacts[-1] for stage in reversed(state.stages) if stage.output_artifacts),
        None,
    )


def reviewable_artifact(state: WorkflowState) -> ArtifactRef | None:
    """Return the immutable work product reviewed by a separate quality artefact."""

    approval_artifact = latest_artifact(state)
    if approval_artifact is None:
        return None
    reviewed_id = str(approval_artifact.metadata.get("reviewed_artifact_id") or "").strip()
    reviewed_checksum = str(
        approval_artifact.metadata.get("reviewed_artifact_checksum") or ""
    ).strip()
    if not reviewed_id:
        return approval_artifact
    candidate = next(
        (
            artifact
            for stage in state.stages
            for artifact in stage.output_artifacts
            if artifact.artifact_id == reviewed_id
        ),
        None,
    )
    if candidate is None or not reviewed_checksum or not candidate.checksum:
        raise InternalReviewDeliveryError("reviewed workflow artefact identity is incomplete")
    if not hmac.compare_digest(candidate.checksum, reviewed_checksum):
        raise InternalReviewDeliveryError("reviewed workflow artefact checksum is stale")
    return candidate


def assert_current_approval_token(state: WorkflowState, supplied: str) -> None:
    expected = workflow_approval_token(state)
    if expected is None:
        raise InternalReviewDeliveryError("workflow run has no current artefact approval gate")
    if not supplied.strip() or not hmac.compare_digest(expected, supplied.strip()):
        raise InternalReviewDeliveryError(
            "approval token is stale or does not match the current workflow gate and artefact version"
        )


def fieldwork_commercial_offer_preview(
    state: WorkflowState, supplied: str, offer: Mapping[str, Any]
) -> dict[str, Any]:
    """Show the immutable commercial offer which must be reviewed before approval."""

    binding = approval_binding_evidence(state, supplied)
    if state.workflow_id != FIELDWORK_PROPOSAL_WORKFLOW_ID:
        raise InternalReviewDeliveryError("commercial offer binding is only valid for the FIELDWORK proposal workflow")
    normalised = _normalise_fieldwork_commercial_offer(state, binding, offer)
    digest = fieldwork_commercial_offer_digest(binding["approval_binding_digest"], normalised)
    return {
        "workflow_id": state.workflow_id,
        "run_id": state.run_id,
        "proposal_artifact_id": normalised["proposal_artifact_id"],
        "proposal_artifact_version": normalised["proposal_artifact_version"],
        "proposal_artifact_checksum": normalised["proposal_artifact_checksum"],
        "commercial_offer": normalised,
        "commercial_offer_digest": digest,
        "approval_token": binding["approval_binding_digest"],
        "external_action_taken": False,
    }


def approval_binding_evidence(
    state: WorkflowState,
    supplied: str,
    *,
    fieldwork_commercial_offer: Mapping[str, Any] | None = None,
    commercial_offer_digest: str = "",
) -> dict[str, Any]:
    """Return the exact, already-validated artefact/gate binding for the audit log."""

    assert_current_approval_token(state, supplied)
    artifact = latest_artifact(state)
    if artifact is None:  # Kept defensive even though token validation requires one.
        raise InternalReviewDeliveryError("workflow run has no current artefact approval gate")
    binding = {
        "workflow_id": state.workflow_id,
        "run_id": state.run_id,
        "stage_id": state.current_stage_id or "",
        "proposed_next_action": state.proposed_next_action or "",
        "artifact_id": artifact.artifact_id,
        "artifact_checksum": artifact.checksum or "",
        "artifact_version": _artifact_version(artifact),
        "approval_binding_digest": supplied.strip(),
    }
    if artifact.metadata.get("reviewed_artifact_id"):
        binding.update(
            {
                "reviewed_artifact_id": str(artifact.metadata.get("reviewed_artifact_id") or ""),
                "reviewed_artifact_checksum": str(
                    artifact.metadata.get("reviewed_artifact_checksum") or ""
                ),
                "reviewed_artifact_version": str(
                    artifact.metadata.get("reviewed_artifact_version") or ""
                ),
            }
        )
    if fieldwork_commercial_offer is not None:
        if state.workflow_id != FIELDWORK_PROPOSAL_WORKFLOW_ID:
            raise InternalReviewDeliveryError("commercial offer binding is only valid for the FIELDWORK proposal workflow")
        offer = _normalise_fieldwork_commercial_offer(state, binding, fieldwork_commercial_offer)
        expected = fieldwork_commercial_offer_digest(binding["approval_binding_digest"], offer)
        if not commercial_offer_digest.strip() or not hmac.compare_digest(expected, commercial_offer_digest.strip()):
            raise InternalReviewDeliveryError("commercial offer digest is stale or does not match the reviewed proposal terms")
        binding["fieldwork_commercial_offer"] = offer
        binding["fieldwork_commercial_offer_digest"] = expected
    return binding


def _normalise_fieldwork_commercial_offer(
    state: WorkflowState, binding: Mapping[str, Any], supplied: Mapping[str, Any]
) -> dict[str, Any]:
    def text(name: str) -> str:
        return str(supplied.get(name) or "").strip()

    def amount(name: str) -> int:
        value = supplied.get(name)
        if isinstance(value, bool):
            raise InternalReviewDeliveryError(f"commercial offer {name} must be an integer amount")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise InternalReviewDeliveryError(f"commercial offer {name} must be an integer amount") from exc
        if result <= 0:
            raise InternalReviewDeliveryError(f"commercial offer {name} must be positive")
        return result

    proposal_id = text("proposal_id")
    recipient_email = text("recipient_email").casefold()
    proposal_url = text("proposal_url")
    scope_summary = text("scope_summary")
    balance_terms = text("balance_terms")
    service_terms_url = text("service_terms_url")
    artifact_id = text("proposal_artifact_id")
    artifact_version = text("proposal_artifact_version")
    artifact_checksum = text("proposal_artifact_checksum").removeprefix("sha256:")
    currency = text("currency").upper()
    if not proposal_id or not recipient_email or "@" not in recipient_email:
        raise InternalReviewDeliveryError("commercial offer requires an exact approved recipient email and proposal ID")
    if not proposal_url.startswith("https://"):
        raise InternalReviewDeliveryError("commercial offer proposal URL must use HTTPS")
    if not scope_summary or not balance_terms:
        raise InternalReviewDeliveryError("commercial offer requires the exact approved scope and balance terms")
    if not service_terms_url.startswith("https://"):
        raise InternalReviewDeliveryError("commercial offer service terms URL must use HTTPS")
    if len(currency) != 3 or not currency.isalpha():
        raise InternalReviewDeliveryError("commercial offer currency must be a three-letter ISO code")
    if (
        artifact_id != str(binding.get("artifact_id") or "")
        or artifact_version != str(binding.get("artifact_version") or "")
        or not artifact_checksum
        or not hmac.compare_digest(artifact_checksum, str(binding.get("artifact_checksum") or "").removeprefix("sha256:"))
    ):
        raise InternalReviewDeliveryError("commercial offer must bind the exact current proposal artefact, version and checksum")
    fixed_investment_minor = amount("fixed_investment_minor")
    deposit_amount_minor = amount("deposit_amount_minor")
    if deposit_amount_minor > fixed_investment_minor:
        raise InternalReviewDeliveryError("commercial offer deposit cannot exceed the fixed investment")
    return {
        "canonical_workspace_id": state.workspace_id,
        "canonical_client_id": state.client_id,
        "proposal_id": proposal_id,
        "recipient_email": recipient_email,
        "proposal_url": proposal_url,
        "scope_summary": scope_summary,
        "balance_terms": balance_terms,
        "service_terms_url": service_terms_url,
        "proposal_artifact_id": artifact_id,
        "proposal_artifact_version": artifact_version,
        "proposal_artifact_checksum": artifact_checksum,
        "fixed_investment_minor": fixed_investment_minor,
        "deposit_amount_minor": deposit_amount_minor,
        "currency": currency,
    }


def fieldwork_commercial_offer_digest(approval_token: str, offer: Mapping[str, Any]) -> str:
    material = json.dumps(
        {"approval_token": approval_token, "commercial_offer": dict(offer)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class InternalReviewDeliveryService:
    """Deliver an immutable workflow artefact to Narratiive's internal reviewer.

    The workflow artefact remains canonical. The email contains a derived review
    copy and is recorded back onto the run using a stable idempotency key. Gmail's
    Message-ID reconciliation protects the send-before-receipt crash window.
    """

    def __init__(
        self,
        workflow_root: str | Path,
        gmail_dispatcher: Callable[[dict[str, Any]], dict[str, Any]] | None,
    ) -> None:
        self.workflow_root = Path(workflow_root).resolve()
        self.gmail_dispatcher = gmail_dispatcher

    def deliver(self, runtime, state: WorkflowState, *, recipient: str) -> dict[str, Any]:
        address = recipient.strip().casefold()
        if address != INTERNAL_REVIEW_ADDRESS:
            raise InternalReviewDeliveryError(
                "internal review delivery is restricted to the exact Narratiive-owned review address"
            )
        at_current_review_gate = (
            state.status is WorkflowStatus.AWAITING_APPROVAL
            and state.approval_status == "pending"
        )
        approved_exact_artifact = (
            state.status is WorkflowStatus.COMPLETE
            and state.approval_status == "approved"
        )
        if not (at_current_review_gate or approved_exact_artifact):
            raise InternalReviewDeliveryError(
                "internal review delivery requires a current human approval gate or an approved exact artefact"
            )
        artifact = reviewable_artifact(state)
        if artifact is None:
            raise InternalReviewDeliveryError("workflow has no persisted artefact to deliver")
        if not self._is_substantial(state, artifact):
            return {
                "status": "telegram_appropriate",
                "substantial": False,
                "delivered": False,
                "approval_token": workflow_approval_token(state),
                "external_action_taken": False,
            }

        output = self._read_artifact(artifact)
        review = HumanReviewPresentationService(
            HumanReviewArtifactStore(self.workflow_root / "human-review-artifacts"),
            allowed_source_root=self.workflow_root,
        ).produce(state=state, source=artifact, output=output)
        key = self._idempotency_key(state, artifact, review, address)
        prior = next(
            (
                item.get("receipt")
                for item in state.external_action_receipts
                if item.get("idempotency_key") == key and isinstance(item.get("receipt"), Mapping)
            ),
            None,
        )
        if prior is not None:
            return self._result(state, artifact, dict(prior), duplicate=True)
        if self.gmail_dispatcher is None:
            return {
                "status": "gmail_dispatcher_unavailable",
                "substantial": True,
                "delivered": False,
                "approval_token": workflow_approval_token(state),
                "external_action_taken": False,
            }

        company = _company_name(state)
        title = review.product
        conclusions = list(review.focus_points)
        review_copy = Path(review.location).read_bytes()
        contract = {
            "worker": "Gmail",
            "execution_mode": "authorised_internal_review_write",
            "approval_granted": False,
            "approval_scope": INTERNAL_REVIEW_APPROVAL_SCOPE,
            "idempotency_key": key,
            "target": {
                "recipient_email": INTERNAL_REVIEW_ADDRESS,
                "company": company,
                "run_id": state.run_id,
                "artifact_id": artifact.artifact_id,
            },
            "payload": {
                "kind": "internal_artifact_review_delivery",
                "recipient_email": INTERNAL_REVIEW_ADDRESS,
                "subject": f"{company} — {title} review",
                "body": _email_body(company, review, approval_status=state.approval_status),
                "attachments": [
                    {
                        "filename": review.filename,
                        "mime_type": review.mime_type,
                        "content_base64": base64.b64encode(review_copy).decode("ascii"),
                    }
                ],
            },
        }
        try:
            evidence = self.gmail_dispatcher(contract)
        except Exception as exc:
            return {
                "status": "gmail_delivery_failed",
                "substantial": True,
                "delivered": False,
                "error": type(exc).__name__,
                "approval_token": workflow_approval_token(state),
                "external_action_taken": False,
            }
        if not isinstance(evidence, Mapping) or evidence.get("sent") is not True or not str(evidence.get("message_id") or "").strip():
            return {
                "status": "gmail_delivery_unverified",
                "substantial": True,
                "delivered": False,
                "approval_token": workflow_approval_token(state),
                "external_action_taken": False,
            }

        receipt = {
            "kind": "internal_artifact_review_delivery",
            "recipient": INTERNAL_REVIEW_ADDRESS,
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "artifact_id": artifact.artifact_id,
            "artifact_checksum": artifact.checksum,
            "artifact_version": _artifact_version(artifact),
            "review_artifact_id": review.review_artifact_id,
            "review_artifact_checksum": review.checksum,
            "review_renderer_id": review.renderer_id,
            "review_renderer_version": review.renderer_version,
            "review_page_count": review.page_count,
            "message_id": str(evidence.get("message_id") or ""),
            "thread_id": str(evidence.get("thread_id") or ""),
            "duplicate_suppressed": evidence.get("duplicate_suppressed") is True,
            "attachment_filename": review.filename,
            "attachment_mime_type": review.mime_type,
            "conclusions": conclusions,
            "decision_prompt": review.decision_prompt,
            "next_if_approved": review.next_if_approved,
            "telegram_notification": review.telegram_notification if at_current_review_gate else "",
        }
        runtime.runs.record_external_action(state.run_id, idempotency_key=key, receipt=receipt)
        current = runtime.runs.load_run(state.run_id)
        return self._result(current, artifact, receipt, duplicate=evidence.get("duplicate_suppressed") is True)

    def _read_artifact(self, artifact: ArtifactRef) -> Mapping[str, Any]:
        location = Path(artifact.location).resolve()
        try:
            location.relative_to(self.workflow_root)
        except ValueError as exc:
            raise InternalReviewDeliveryError("workflow artefact is outside the authoritative runtime root") from exc
        try:
            value = json.loads(location.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InternalReviewDeliveryError("workflow artefact is unreadable") from exc
        if not isinstance(value, Mapping):
            raise InternalReviewDeliveryError("workflow artefact must be structured")
        checksum = hashlib.sha256(
            json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if not artifact.checksum or not hmac.compare_digest(artifact.checksum, checksum):
            raise InternalReviewDeliveryError("workflow artefact checksum does not match its immutable record")
        return value

    @staticmethod
    def _is_substantial(state: WorkflowState, artifact: ArtifactRef) -> bool:
        if artifact.artifact_type.strip().casefold() in SUBSTANTIAL_ARTIFACT_TYPES:
            return True
        return state.workflow_id in {
            "growth_diagnostic_to_blueprint_lite",
            "blueprint_lite_to_discovery_preparation",
            "discovery_evidence_to_growth_sprint_proposal",
            "strategic_synthesis_to_strategy_thesis",
            "strategy_thesis_to_growth_blueprint",
            "research_to_growth_blueprint",
            "growth_blueprint_deliverable_production",
        }

    @staticmethod
    def _idempotency_key(
        state: WorkflowState,
        artifact: ArtifactRef,
        review: HumanReviewArtifact,
        recipient: str,
    ) -> str:
        material = "\0".join(
            (
                INTERNAL_REVIEW_APPROVAL_SCOPE,
                state.workspace_id,
                state.client_id,
                state.run_id,
                artifact.artifact_id,
                artifact.checksum or "",
                review.review_artifact_id,
                review.checksum,
                review.renderer_version,
                recipient,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _result(
        state: WorkflowState,
        artifact: ArtifactRef,
        receipt: Mapping[str, Any],
        *,
        duplicate: bool,
    ) -> dict[str, Any]:
        return {
            "status": "internal_review_delivered",
            "substantial": True,
            "delivered": True,
            "duplicate_suppressed": duplicate,
            "recipient": INTERNAL_REVIEW_ADDRESS,
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "artifact_id": artifact.artifact_id,
            "artifact_checksum": artifact.checksum,
            "artifact_version": _artifact_version(artifact),
            "review_artifact_id": str(receipt.get("review_artifact_id") or ""),
            "review_artifact_checksum": str(receipt.get("review_artifact_checksum") or ""),
            "review_renderer_id": str(receipt.get("review_renderer_id") or ""),
            "review_renderer_version": str(receipt.get("review_renderer_version") or ""),
            "review_page_count": int(receipt.get("review_page_count") or 0),
            "attachment_filename": str(receipt.get("attachment_filename") or ""),
            "attachment_mime_type": str(receipt.get("attachment_mime_type") or ""),
            "message_id": str(receipt.get("message_id") or ""),
            "thread_id": str(receipt.get("thread_id") or ""),
            "conclusions": list(receipt.get("conclusions") or []),
            "decision_prompt": str(receipt.get("decision_prompt") or ""),
            "next_if_approved": str(receipt.get("next_if_approved") or ""),
            "telegram_notification": (
                "" if state.approval_status == "approved"
                else str(receipt.get("telegram_notification") or "")
            ),
            "review_link": "https://mail.google.com/mail/u/0/#all/" + quote(str(receipt.get("thread_id") or receipt.get("message_id") or ""), safe=""),
            "approval_token": workflow_approval_token(state),
            "approval_status": state.approval_status,
            "external_action_taken": not duplicate,
        }


def _artifact_version(artifact: ArtifactRef) -> str:
    value = str(artifact.metadata.get("version") or "").strip()
    if value:
        return f"v{value.removeprefix('v')}"
    return "v1"


def _company_name(state: WorkflowState) -> str:
    payload = state.input_payload
    for value in (
        payload.get("company"),
        payload.get("company_name"),
        (payload.get("commercial_context") or {}).get("company") if isinstance(payload.get("commercial_context"), Mapping) else None,
        (payload.get("client_context") or {}).get("name") if isinstance(payload.get("client_context"), Mapping) else None,
    ):
        if str(value or "").strip():
            return str(value).strip()
    return state.entity_id or state.client_id


def _email_body(company: str, review: HumanReviewArtifact, *, approval_status: str) -> str:
    compact = lambda value: " ".join(str(value).split())[:240]
    next_step = (
        "This exact artefact is already approved. No next workflow stage has been started by this review delivery."
        if approval_status == "approved"
        else "Approval is pending. Please approve or request changes through Tony in Telegram."
    )
    return "\n".join((
        f"{compact(company)} — {compact(review.product)} is attached for review.",
        next_step,
        f"Next, if approved: {compact(review.next_if_approved)}",
    ))
