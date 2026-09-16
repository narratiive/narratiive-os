from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def latest_artifact(state: WorkflowState) -> ArtifactRef | None:
    return next(
        (stage.output_artifacts[-1] for stage in reversed(state.stages) if stage.output_artifacts),
        None,
    )


def assert_current_approval_token(state: WorkflowState, supplied: str) -> None:
    expected = workflow_approval_token(state)
    if expected is None:
        raise InternalReviewDeliveryError("workflow run has no current artefact approval gate")
    if not supplied.strip() or not hmac.compare_digest(expected, supplied.strip()):
        raise InternalReviewDeliveryError(
            "approval token is stale or does not match the current workflow gate and artefact version"
        )


def approval_binding_evidence(state: WorkflowState, supplied: str) -> dict[str, str]:
    """Return the exact, already-validated artefact/gate binding for the audit log."""

    assert_current_approval_token(state, supplied)
    artifact = latest_artifact(state)
    if artifact is None:  # Kept defensive even though token validation requires one.
        raise InternalReviewDeliveryError("workflow run has no current artefact approval gate")
    return {
        "workflow_id": state.workflow_id,
        "run_id": state.run_id,
        "stage_id": state.current_stage_id or "",
        "proposed_next_action": state.proposed_next_action or "",
        "artifact_id": artifact.artifact_id,
        "artifact_checksum": artifact.checksum or "",
        "artifact_version": _artifact_version(artifact),
        "approval_binding_digest": supplied.strip(),
    }


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
        if state.status is not WorkflowStatus.AWAITING_APPROVAL or state.approval_status != "pending":
            raise InternalReviewDeliveryError("internal review delivery requires a current human approval gate")
        artifact = latest_artifact(state)
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
                "body": _email_body(company, review),
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
            "telegram_notification": review.telegram_notification,
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
            "telegram_notification": str(receipt.get("telegram_notification") or ""),
            "approval_token": workflow_approval_token(state),
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


def _email_body(company: str, review: HumanReviewArtifact) -> str:
    lines = [
        f"The {review.product} for {company} is ready for internal review.",
        "",
        "The polished PDF review copy is attached.",
    ]
    if review.focus_points:
        lines.extend(("", "Please pay particular attention to:"))
        lines.extend(f"- {item}" for item in review.focus_points[:4])
    lines.extend(
        (
            "",
            "Approval status: Pending.",
            f"If approved: {review.next_if_approved}",
            "",
            "Please give Tony your approval, rejection or revision direction in Telegram.",
        )
    )
    return "\n".join(lines)
