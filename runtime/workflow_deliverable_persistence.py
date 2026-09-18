from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from runtime.models import ArtifactRef, WorkflowState, WorkflowStatus


class WorkflowDeliverablePersistenceError(ValueError):
    pass


class WorkflowDeliverablePersistenceService:
    """Preview and execute exact, approval-bound internal Drive persistence."""

    def __init__(
        self,
        workflow_root: str | Path,
        drive_dispatcher: Callable[[dict[str, Any]], dict[str, Any]] | None,
    ) -> None:
        self.workflow_root = Path(workflow_root).resolve()
        self.drive_dispatcher = drive_dispatcher

    def preview(self, state: WorkflowState, *, drive_folder_id: str) -> dict[str, Any]:
        folder_id = drive_folder_id.strip()
        if state.workflow_id != "growth_blueprint_deliverable_production":
            raise WorkflowDeliverablePersistenceError("Drive persistence is only supported for a Growth Blueprint deliverable")
        if state.status is not WorkflowStatus.COMPLETE or state.approval_status != "approved":
            raise WorkflowDeliverablePersistenceError("Growth Blueprint deliverable must be approved before Drive persistence")
        if not folder_id:
            raise WorkflowDeliverablePersistenceError("verified Drive folder identifier is required")
        artifact, output = self._artifact_output(state)
        files = (
            self._file(output, "editable_pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            self._file(output, "review_pdf", "application/pdf"),
        )
        action = {
            "kind": "persist_reviewed_growth_blueprint_files",
            "source_workflow": state.workflow_id,
            "source_run_id": state.run_id,
            "source_artifact_id": artifact.artifact_id,
            "source_artifact_checksum": artifact.checksum or "",
            "workspace_id": state.workspace_id,
            "client_id": state.client_id,
            "drive_folder_id": folder_id,
            "files": list(files),
            "sharing": "not_authorised",
            "client_notification": "not_authorised",
            "publication": "not_authorised",
        }
        digest = _digest(action)
        prior = _existing_receipt(state, digest)
        return {
            **action,
            "action_digest": digest,
            "approval_status": "executed" if prior else "pending",
            "execution_status": "persisted" if prior else "not_dispatched",
            "drive_receipt": prior,
            "external_action_taken": False,
        }

    def execute(
        self,
        runtime,
        state: WorkflowState,
        *,
        drive_folder_id: str,
        action_digest: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        if not approver.strip() or not rationale.strip():
            raise WorkflowDeliverablePersistenceError("Drive persistence requires an authenticated approver and rationale")
        preview = self.preview(state, drive_folder_id=drive_folder_id)
        expected = str(preview["action_digest"])
        if not action_digest.strip() or not hmac.compare_digest(expected, action_digest.strip()):
            raise WorkflowDeliverablePersistenceError("Drive approval is stale or does not match the exact files and target folder")
        prior = preview.get("drive_receipt")
        if isinstance(prior, Mapping):
            return self._result(preview, prior, duplicate=True)
        if self.drive_dispatcher is None:
            raise WorkflowDeliverablePersistenceError("Google Drive dispatcher is unavailable")

        file_receipts = []
        for file in preview["files"]:
            file_digest = hashlib.sha256(f"{expected}:{file['checksum']}:{file['filename']}".encode("utf-8")).hexdigest()
            contract = {
                "worker": "Google Drive",
                "execution_mode": "approval_gated_write",
                "approval_granted": True,
                "approval_scope": "reviewed_growth_blueprint_files_to_verified_workspace",
                "idempotency_key": file_digest,
                "target": {
                    "drive_folder_id": preview["drive_folder_id"],
                    "workspace_id": state.workspace_id,
                    "client_id": state.client_id,
                    "run_id": state.run_id,
                },
                "payload": {
                    "kind": "reviewed_growth_blueprint_file",
                    "parent_folder_id": preview["drive_folder_id"],
                    "filename": file["filename"],
                    "local_path": file["local_path"],
                    "checksum": file["checksum"],
                    "mime_type": file["mime_type"],
                },
            }
            evidence = self.drive_dispatcher(contract)
            if not isinstance(evidence, Mapping) or evidence.get("verified") is not True:
                raise WorkflowDeliverablePersistenceError(f"Drive did not verify {file['filename']}")
            file_id = str(evidence.get("file_id") or "").strip()
            file_url = str(evidence.get("file_url") or evidence.get("url") or "").strip()
            if not file_id or not file_url or str(evidence.get("checksum") or "") != file["checksum"]:
                raise WorkflowDeliverablePersistenceError(f"Drive evidence is incomplete for {file['filename']}")
            file_receipts.append({
                "filename": file["filename"],
                "mime_type": file["mime_type"],
                "checksum": file["checksum"],
                "file_id": file_id,
                "file_url": file_url,
                "duplicate_suppressed": evidence.get("duplicate_suppressed") is True,
            })
        receipt = {
            "kind": preview["kind"],
            "action_digest": expected,
            "approval_scope": "reviewed_growth_blueprint_files_to_verified_workspace",
            "approved_by": approver.strip(),
            "approval_rationale": rationale.strip(),
            "source_artifact_id": preview["source_artifact_id"],
            "source_artifact_checksum": preview["source_artifact_checksum"],
            "drive_folder_id": preview["drive_folder_id"],
            "files": file_receipts,
            "sharing": "not_authorised",
            "client_notification": "not_authorised",
            "publication": "not_authorised",
        }
        updated = runtime.runs.record_external_action(state.run_id, idempotency_key=expected, receipt=receipt)
        projection = getattr(runtime, "business_projection", None)
        if projection is not None:
            projection.prepare(updated)
        return self._result(preview, receipt, duplicate=all(item["duplicate_suppressed"] for item in file_receipts))

    def _artifact_output(self, state: WorkflowState) -> tuple[ArtifactRef, Mapping[str, Any]]:
        artifacts = [artifact for stage in state.stages for artifact in stage.output_artifacts]
        if not artifacts:
            raise WorkflowDeliverablePersistenceError("workflow has no persisted deliverable artefact")
        artifact = artifacts[-1]
        location = Path(artifact.location).resolve()
        try:
            location.relative_to(self.workflow_root)
            value = json.loads(location.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise WorkflowDeliverablePersistenceError("deliverable artefact is unavailable or outside the workflow root") from exc
        if not isinstance(value, Mapping):
            raise WorkflowDeliverablePersistenceError("deliverable artefact must be structured")
        checksum = hashlib.sha256(json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not artifact.checksum or not hmac.compare_digest(checksum, artifact.checksum):
            raise WorkflowDeliverablePersistenceError("deliverable artefact checksum does not match its immutable record")
        return artifact, value

    def _file(self, output: Mapping[str, Any], field: str, mime_type: str) -> dict[str, Any]:
        location = Path(str(output.get(field) or "")).resolve()
        try:
            location.relative_to(self.workflow_root)
        except ValueError as exc:
            raise WorkflowDeliverablePersistenceError(f"{field} is outside the authoritative workflow root") from exc
        if not location.is_file():
            raise WorkflowDeliverablePersistenceError(f"{field} is unavailable")
        content = location.read_bytes()
        return {
            "field": field,
            "filename": location.name,
            "local_path": str(location),
            "mime_type": mime_type,
            "checksum": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    @staticmethod
    def _result(preview: Mapping[str, Any], receipt: Mapping[str, Any], *, duplicate: bool) -> dict[str, Any]:
        return {
            "status": "growth_blueprint_files_persisted",
            "source_run_id": preview["source_run_id"],
            "source_artifact_id": preview["source_artifact_id"],
            "drive_folder_id": preview["drive_folder_id"],
            "action_digest": preview["action_digest"],
            "files": list(receipt.get("files") or []),
            "duplicate_suppressed": duplicate,
            "sharing": "not_authorised",
            "client_notification": "not_authorised",
            "publication": "not_authorised",
            "external_action_taken": not duplicate,
            "execution_truth": "verified_executed",
        }


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _existing_receipt(state: WorkflowState, digest: str) -> dict[str, Any] | None:
    for item in state.external_action_receipts:
        receipt = item.get("receipt")
        if item.get("idempotency_key") == digest and isinstance(receipt, Mapping):
            return dict(receipt)
    return None
