from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from runtime.models import ArtifactRef, WorkflowState, WorkflowStatus


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
        key = self._idempotency_key(state, artifact, address)
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
        title = _artifact_title(state, artifact)
        conclusions = _conclusions(output)
        review_copy = _render_review_copy(company, title, state, artifact, output)
        filename = f"{_safe_filename(company)}-{_safe_filename(title)}-{_artifact_version(artifact)}.html"
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
                "body": _email_body(company, title, conclusions),
                "attachments": [
                    {
                        "filename": filename,
                        "mime_type": "text/html",
                        "content_base64": base64.b64encode(review_copy.encode("utf-8")).decode("ascii"),
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
            "message_id": str(evidence.get("message_id") or ""),
            "thread_id": str(evidence.get("thread_id") or ""),
            "duplicate_suppressed": evidence.get("duplicate_suppressed") is True,
            "attachment_filename": filename,
            "conclusions": conclusions,
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
        }

    @staticmethod
    def _idempotency_key(state: WorkflowState, artifact: ArtifactRef, recipient: str) -> str:
        material = "\0".join(
            (
                INTERNAL_REVIEW_APPROVAL_SCOPE,
                state.workspace_id,
                state.client_id,
                state.run_id,
                artifact.artifact_id,
                artifact.checksum or "",
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
            "message_id": str(receipt.get("message_id") or ""),
            "thread_id": str(receipt.get("thread_id") or ""),
            "conclusions": list(receipt.get("conclusions") or []),
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
        (payload.get("client_context") or {}).get("name") if isinstance(payload.get("client_context"), Mapping) else None,
    ):
        if str(value or "").strip():
            return str(value).strip()
    return state.entity_id or state.client_id


def _artifact_title(state: WorkflowState, artifact: ArtifactRef) -> str:
    names = {
        "blueprint_lite": "Blueprint Lite",
        "discovery_synthesis": "Discovery synthesis",
        "growth_sprint_proposal": "Growth Sprint proposal",
        "strategy_thesis": "Strategy Thesis",
        "growth_blueprint": "Growth Blueprint",
        "campaign_world": "Campaign World",
        "creative_directors_bible": "Creative Director's Bible",
        "research_report": "research report",
    }
    workflow_names = {
        "growth_diagnostic_to_blueprint_lite": "Blueprint Lite",
        "blueprint_lite_to_discovery_preparation": "Discovery synthesis",
        "discovery_evidence_to_growth_sprint_proposal": "Growth Sprint proposal",
        "research_to_growth_blueprint": "Growth Blueprint",
    }
    return names.get(
        artifact.artifact_type.casefold(),
        workflow_names.get(state.workflow_id, artifact.artifact_type.replace("_", " ").title()),
    )


def _conclusions(output: Mapping[str, Any]) -> list[str]:
    candidates = (
        "central_diagnosis",
        "growth_tension",
        "provisional_opportunity",
        "growth_opportunity",
        "strategy_thesis",
        "recommendation",
    )
    result: list[str] = []
    for key in candidates:
        text = _compact_value(output.get(key))
        if text and text.casefold() not in {item.casefold() for item in result}:
            result.append(text[:420].rstrip())
        if len(result) == 4:
            break
    if len(result) < 2:
        for key, value in output.items():
            if key in {"source_backed_evidence", "sources", "fact_interpretation_hypothesis_lineage", "blueprint_lite"}:
                continue
            text = _compact_value(value)
            if text and text.casefold() not in {item.casefold() for item in result}:
                result.append(text[:420].rstrip())
            if len(result) == 4:
                break
    return result[:4]


def _compact_value(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return "; ".join(" ".join(str(item).split()) for item in value[:3] if str(item).strip())
    if isinstance(value, Mapping):
        return "; ".join(
            f"{str(key).replace('_', ' ')}: {_compact_value(item)}"
            for key, item in list(value.items())[:3]
            if _compact_value(item)
        )
    return ""


def _email_body(company: str, title: str, conclusions: list[str]) -> str:
    lines = [
        f"The {title} for {company} is ready for internal review.",
        "",
        "The full immutable review copy is attached. Narratiive OS remains the source of truth for the artefact and approval state.",
    ]
    if conclusions:
        lines.extend(("", "Review focus:"))
        lines.extend(f"- {item}" for item in conclusions)
    lines.extend(("", "Please give the approval, rejection or revision direction to Tony in Telegram."))
    return "\n".join(lines)


def _render_review_copy(
    company: str,
    title: str,
    state: WorkflowState,
    artifact: ArtifactRef,
    output: Mapping[str, Any],
) -> str:
    sections = "".join(
        f"<section><h2>{html.escape(str(key).replace('_', ' ').title())}</h2>{_html_value(value)}</section>"
        for key, value in output.items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(company)} — {html.escape(title)}</title>
<style>
body{{margin:0;background:#f4f1e9;color:#181818;font:16px/1.55 Arial,sans-serif}}main{{max-width:820px;margin:0 auto;background:#fff;min-height:100vh;padding:64px 72px;box-sizing:border-box}}header{{border-bottom:5px solid #181818;padding-bottom:28px;margin-bottom:42px}}.eyebrow{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#6b665d}}h1{{font:700 42px/1.05 Georgia,serif;margin:12px 0}}h2{{font:700 23px/1.2 Georgia,serif;margin:0 0 12px}}section{{border-top:1px solid #d8d3c8;padding:28px 0}}ul{{padding-left:22px}}li{{margin:8px 0}}.meta{{color:#6b665d;font-size:13px}}code{{font-size:12px}}@media(max-width:700px){{main{{padding:36px 24px}}h1{{font-size:34px}}}}
</style></head><body><main><header><div class="eyebrow">Narratiive internal review · not for client distribution</div><h1>{html.escape(company)}<br>{html.escape(title)}</h1><div class="meta">Workflow {html.escape(state.run_id)} · {_artifact_version(artifact)} · artefact {html.escape(artifact.artifact_id)}</div></header>{sections}</main></body></html>"""


def _html_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return "".join(
            f"<h3>{html.escape(str(key).replace('_', ' ').title())}</h3>{_html_value(item)}"
            for key, item in value.items()
        )
    if isinstance(value, list):
        return "<ul>" + "".join(f"<li>{_html_value(item)}</li>" for item in value) + "</ul>"
    text = html.escape(str(value if value is not None else ""))
    return "".join(f"<p>{line}</p>" for line in text.splitlines() if line.strip()) or "<p>—</p>"


def _safe_filename(value: str) -> str:
    cleaned = "-".join("".join(character for character in word if character.isalnum()) for word in value.split())
    return cleaned.strip("-")[:80] or "Narratiive-review"
