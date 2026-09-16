from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from runtime.models import ArtifactRef, WorkflowState
from runtime.tony_internal_review_delivery import INTERNAL_REVIEW_ADDRESS, latest_artifact


SIMULATED_CLIENT_ACTION_SCOPE = "narratiive_simulated_client_action"


class WorkflowActionPreviewError(ValueError):
    pass


class WorkflowActionPreviewService:
    """Resolve and execute a version-bound client-action simulation.

    The workflow artefact remains canonical.  A preview contains only business-facing
    fields and a reference to the derived review PDF; it never grants permission to
    send.  Execution recomputes the preview and requires its exact digest, so any
    change to the recipient, body, attachment or source artefact invalidates approval.
    """

    def __init__(
        self,
        workflow_root: str | Path,
        gmail_dispatcher: Callable[[dict[str, Any]], dict[str, Any]] | None,
    ) -> None:
        self.workflow_root = Path(workflow_root).resolve()
        self.gmail_dispatcher = gmail_dispatcher

    def artifact_detail(self, state: WorkflowState) -> dict[str, Any]:
        artifact, output = self._artifact_output(state)
        review = self._review_artifact(state, artifact)
        return {
            "current_workflow": state.workflow_id,
            "current_lifecycle_stage": _lifecycle_stage(state.workflow_id),
            "run_id": state.run_id,
            "client_id": state.client_id,
            "client_name": _company_name(state),
            "workflow_status": state.status.value,
            "approval_status": state.approval_status,
            "approved_artifact": {
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact.artifact_type,
                "artifact_checksum": artifact.checksum or "",
                "artifact_version": _artifact_version(artifact),
            },
            "human_review_artifact": review,
            "draft_client_communication": output.get("draft_client_communication"),
            "commercial_proposal_inputs": output.get("commercial_proposal_inputs"),
            "evidence_summary": _evidence_summary(output),
            "delivery_state": _delivery_state(state, artifact),
            "external_action_taken": False,
        }

    def preview_simulated_email(
        self,
        state: WorkflowState,
        *,
        simulation_mode: bool,
        delivery_override: str,
    ) -> dict[str, Any]:
        if simulation_mode is not True:
            raise WorkflowActionPreviewError(
                "real client delivery is not enabled; prepare an explicit simulation or use a future governed adapter"
            )
        if delivery_override.strip().casefold() != INTERNAL_REVIEW_ADDRESS:
            raise WorkflowActionPreviewError(
                "simulation delivery override must be the authorised Narratiive internal address"
            )
        if state.workflow_id != "discovery_evidence_to_growth_sprint_proposal":
            raise WorkflowActionPreviewError("client email preview is only supported for a Growth Sprint proposal")
        if state.approval_status != "approved":
            raise WorkflowActionPreviewError("Growth Sprint proposal must be approved before a client action is prepared")
        artifact, output = self._artifact_output(state)
        source_body = str(output.get("draft_client_communication") or "").strip()
        if not source_body:
            raise WorkflowActionPreviewError("approved artefact has no draft client communication")
        review = self._review_artifact(state, artifact)
        if not review:
            raise WorkflowActionPreviewError("approved artefact has no polished human-review PDF")
        company = _company_name(state)
        recipient_name = _intended_recipient_name(state, company)
        body = _resolve_simulation_body(source_body, recipient_name)
        action = {
            "kind": "simulated_growth_sprint_proposal_email",
            "simulation_mode": True,
            "intended_client": company,
            "intended_recipient_name": recipient_name,
            "delivery_override": INTERNAL_REVIEW_ADDRESS,
            "recipient_name": recipient_name,
            "recipient_email": INTERNAL_REVIEW_ADDRESS,
            "cc": [],
            "bcc": [],
            "subject": f"{company} — Growth Sprint Proposal",
            "body_description": _body_description(body),
            "full_body": body,
            "body_source_field": "draft_client_communication",
            "attachments": [
                {
                    "review_artifact_id": review["review_artifact_id"],
                    "filename": review["filename"],
                    "mime_type": review["mime_type"],
                    "checksum": review["checksum"],
                    "page_count": review["page_count"],
                }
            ],
            "source_workflow": state.workflow_id,
            "source_run_id": state.run_id,
            "source_artifact_id": artifact.artifact_id,
            "source_artifact_checksum": artifact.checksum or "",
            "source_artifact_version": _artifact_version(artifact),
            "intended_consequence": (
                "Deliver an internal simulation of the approved client communication and polished proposal PDF; "
                "no KatKin person or domain will be contacted."
            ),
        }
        digest = _digest(action)
        receipt = _existing_receipt(state, digest)
        return {
            **action,
            "action_digest": digest,
            "approval_status": "executed" if receipt else "pending",
            "execution_status": "delivered" if receipt else "not_dispatched",
            "delivery_receipt": receipt,
            "external_action_taken": False,
        }

    def execute_simulated_email(
        self,
        runtime,
        state: WorkflowState,
        *,
        action_digest: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        if not approver.strip() or not rationale.strip():
            raise WorkflowActionPreviewError("simulated send requires an authenticated approver and rationale")
        preview = self.preview_simulated_email(
            state,
            simulation_mode=True,
            delivery_override=INTERNAL_REVIEW_ADDRESS,
        )
        expected = str(preview["action_digest"])
        if not action_digest.strip() or not hmac.compare_digest(expected, action_digest.strip()):
            raise WorkflowActionPreviewError("action approval is stale or does not match the resolved payload and artefact version")
        prior = preview.get("delivery_receipt")
        if isinstance(prior, Mapping):
            return self._execution_result(preview, prior, duplicate=True)
        if self.gmail_dispatcher is None:
            raise WorkflowActionPreviewError("Gmail dispatcher is unavailable")

        review = preview["attachments"][0]
        pdf_path = self._review_location(state, str(review["review_artifact_id"]))
        pdf_bytes = pdf_path.read_bytes()
        checksum = hashlib.sha256(pdf_bytes).hexdigest()
        if not hmac.compare_digest(checksum, str(review["checksum"])):
            raise WorkflowActionPreviewError("human-review PDF checksum no longer matches its immutable manifest")
        contract = {
            "worker": "Gmail",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": SIMULATED_CLIENT_ACTION_SCOPE,
            "idempotency_key": expected,
            "target": {
                "recipient_email": INTERNAL_REVIEW_ADDRESS,
                "company": preview["intended_client"],
                "run_id": state.run_id,
                "artifact_id": preview["source_artifact_id"],
            },
            "payload": {
                "kind": preview["kind"],
                "recipient_email": INTERNAL_REVIEW_ADDRESS,
                "subject": preview["subject"],
                "body": preview["full_body"],
                "attachments": [
                    {
                        "filename": review["filename"],
                        "mime_type": review["mime_type"],
                        "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                    }
                ],
            },
        }
        evidence = self.gmail_dispatcher(contract)
        if not isinstance(evidence, Mapping) or evidence.get("sent") is not True:
            raise WorkflowActionPreviewError("Gmail did not return verified send evidence")
        message_id = str(evidence.get("message_id") or "").strip()
        if not message_id:
            raise WorkflowActionPreviewError("Gmail send evidence has no message identifier")
        receipt = {
            "kind": preview["kind"],
            "simulation_mode": True,
            "intended_client": preview["intended_client"],
            "delivery_override": INTERNAL_REVIEW_ADDRESS,
            "recipient": INTERNAL_REVIEW_ADDRESS,
            "subject": preview["subject"],
            "action_digest": expected,
            "approval_scope": SIMULATED_CLIENT_ACTION_SCOPE,
            "approved_by": approver,
            "approval_rationale": rationale,
            "source_artifact_id": preview["source_artifact_id"],
            "source_artifact_checksum": preview["source_artifact_checksum"],
            "source_artifact_version": preview["source_artifact_version"],
            "review_artifact_id": review["review_artifact_id"],
            "attachment_filename": review["filename"],
            "attachment_checksum": review["checksum"],
            "message_id": message_id,
            "thread_id": str(evidence.get("thread_id") or ""),
            "duplicate_suppressed": evidence.get("duplicate_suppressed") is True,
        }
        runtime.runs.record_external_action(state.run_id, idempotency_key=expected, receipt=receipt)
        return self._execution_result(preview, receipt, duplicate=evidence.get("duplicate_suppressed") is True)

    def _artifact_output(self, state: WorkflowState) -> tuple[ArtifactRef, Mapping[str, Any]]:
        artifact = latest_artifact(state)
        if artifact is None:
            raise WorkflowActionPreviewError("workflow has no persisted artefact")
        location = Path(artifact.location).resolve()
        try:
            location.relative_to(self.workflow_root)
        except ValueError as exc:
            raise WorkflowActionPreviewError("workflow artefact is outside the authoritative runtime root") from exc
        try:
            value = json.loads(location.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkflowActionPreviewError("workflow artefact is unreadable") from exc
        if not isinstance(value, Mapping):
            raise WorkflowActionPreviewError("workflow artefact must be structured")
        checksum = hashlib.sha256(json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not artifact.checksum or not hmac.compare_digest(checksum, artifact.checksum):
            raise WorkflowActionPreviewError("workflow artefact checksum does not match its immutable record")
        return artifact, value

    def _review_artifact(self, state: WorkflowState, artifact: ArtifactRef) -> dict[str, Any] | None:
        receipts = [
            item.get("receipt") for item in state.external_action_receipts
            if isinstance(item.get("receipt"), Mapping)
            and item["receipt"].get("kind") == "internal_artifact_review_delivery"
            and item["receipt"].get("artifact_id") == artifact.artifact_id
            and str(item["receipt"].get("attachment_mime_type") or "") == "application/pdf"
        ]
        if not receipts:
            return None
        receipt = receipts[-1]
        review_id = str(receipt.get("review_artifact_id") or "")
        location = self._review_location(state, review_id)
        manifest_path = location.parent / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkflowActionPreviewError("human-review manifest is unreadable") from exc
        if not isinstance(manifest, Mapping) or str(manifest.get("source_artifact_id") or "") != artifact.artifact_id:
            raise WorkflowActionPreviewError("human-review manifest is not bound to the approved artefact")
        checksum = hashlib.sha256(location.read_bytes()).hexdigest()
        if not hmac.compare_digest(checksum, str(manifest.get("checksum") or "")):
            raise WorkflowActionPreviewError("human-review PDF checksum does not match its manifest")
        return {
            "review_artifact_id": review_id,
            "filename": str(manifest.get("filename") or location.name),
            "mime_type": "application/pdf",
            "checksum": checksum,
            "page_count": int(manifest.get("page_count") or 0),
            "renderer_id": str(manifest.get("renderer_id") or ""),
            "renderer_version": str(manifest.get("renderer_version") or ""),
        }

    def _review_location(self, state: WorkflowState, review_id: str) -> Path:
        if not review_id or "/" in review_id or "\\" in review_id:
            raise WorkflowActionPreviewError("human-review artefact identity is invalid")
        directory = self.workflow_root / "human-review-artifacts" / state.workspace_id / state.client_id / review_id
        manifest_path = directory / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            location = Path(str(manifest.get("location") or "")).resolve()
            location.relative_to(directory.resolve())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise WorkflowActionPreviewError("human-review artefact is unavailable") from exc
        if not location.is_file():
            raise WorkflowActionPreviewError("human-review PDF is unavailable")
        return location

    @staticmethod
    def _execution_result(preview: Mapping[str, Any], receipt: Mapping[str, Any], *, duplicate: bool) -> dict[str, Any]:
        return {
            "status": "simulated_client_action_delivered",
            "simulation_mode": True,
            "intended_client": preview["intended_client"],
            "delivery_override": INTERNAL_REVIEW_ADDRESS,
            "recipient": INTERNAL_REVIEW_ADDRESS,
            "subject": preview["subject"],
            "source_artifact_id": preview["source_artifact_id"],
            "source_artifact_version": preview["source_artifact_version"],
            "action_digest": preview["action_digest"],
            "message_id": str(receipt.get("message_id") or ""),
            "thread_id": str(receipt.get("thread_id") or ""),
            "attachment_filename": str(receipt.get("attachment_filename") or ""),
            "duplicate_suppressed": duplicate,
            "external_action_taken": not duplicate,
            "execution_truth": "verified_executed",
        }


def _artifact_version(artifact: ArtifactRef) -> str:
    value = str(artifact.metadata.get("version") or "").strip()
    return f"v{value.removeprefix('v')}" if value else "v1"


def _company_name(state: WorkflowState) -> str:
    payload = state.input_payload
    contexts = [payload.get("commercial_context"), payload.get("client_context")]
    values = [payload.get("company"), payload.get("company_name")]
    for context in contexts:
        if isinstance(context, Mapping):
            values.extend((context.get("company"), context.get("name")))
    return next((str(value).strip() for value in values if str(value or "").strip()), state.client_id)


def _intended_recipient_name(state: WorkflowState, company: str) -> str:
    context = state.input_payload.get("commercial_context")
    if isinstance(context, Mapping):
        for key in ("contact_name", "contact", "recipient_name"):
            if str(context.get(key) or "").strip():
                return str(context[key]).strip()
    return f"{company} team"


def _lifecycle_stage(workflow_id: str) -> str:
    return {
        "growth_diagnostic_to_blueprint_lite": "blueprint_lite",
        "blueprint_lite_to_discovery_preparation": "discovery",
        "discovery_evidence_to_growth_sprint_proposal": "growth_sprint_proposal",
        "growth_sprint_to_research_engine": "research",
        "research_to_growth_blueprint": "growth_blueprint",
    }.get(workflow_id, "workflow")


def _evidence_summary(output: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: output[key]
        for key in (
            "central_diagnosis",
            "growth_opportunity",
            "evidence_gaps",
            "assumptions_and_dependencies",
            "diagnostic_input_coverage",
        )
        if key in output
    }


def _delivery_state(state: WorkflowState, artifact: ArtifactRef) -> dict[str, Any]:
    receipts = [
        dict(item["receipt"])
        for item in state.external_action_receipts
        if isinstance(item.get("receipt"), Mapping)
        and (
            item["receipt"].get("artifact_id") == artifact.artifact_id
            or item["receipt"].get("source_artifact_id") == artifact.artifact_id
        )
    ]
    return {
        "internal_review_delivered": any(item.get("kind") == "internal_artifact_review_delivery" for item in receipts),
        "simulated_client_action_delivered": any(item.get("kind") == "simulated_growth_sprint_proposal_email" for item in receipts),
        "receipts": [
            {
                key: item.get(key)
                for key in (
                    "kind", "recipient", "delivery_override", "message_id", "thread_id",
                    "attachment_filename", "duplicate_suppressed", "action_digest",
                )
                if item.get(key) not in (None, "")
            }
            for item in receipts
        ],
    }


def _body_description(body: str) -> str:
    compact = " ".join(body.split())
    return compact[:240] + ("…" if len(compact) > 240 else "")


def _resolve_simulation_body(source_body: str, recipient_name: str) -> str:
    body = source_body.strip()
    marker = "DRAFT — INTERNAL, FOR HUMAN REVIEW ONLY. NOT SENT TO CLIENT."
    if body.startswith(marker):
        body = body[len(marker):].lstrip()
    body = body.replace("[Founder name]", recipient_name)
    closing = (
        "This message is a draft prepared for internal review; it has not been sent, "
        "and no commercial terms have been agreed."
    )
    if body.endswith(closing):
        body = body[: -len(closing)].rstrip()
    unresolved = re.findall(r"\[[^\]\n]{1,100}\]", body)
    if unresolved:
        raise WorkflowActionPreviewError(
            "proposed client communication still has unresolved fields: " + ", ".join(unresolved)
        )
    if not body:
        raise WorkflowActionPreviewError("proposed client communication is empty after editorial resolution")
    return body


def _digest(action: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(action), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _existing_receipt(state: WorkflowState, digest: str) -> dict[str, Any] | None:
    for item in state.external_action_receipts:
        receipt = item.get("receipt")
        if item.get("idempotency_key") == digest and isinstance(receipt, Mapping):
            return dict(receipt)
    return None
