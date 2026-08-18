from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintRevisionDeliveryCommandService:
    """Redeliver only a verified persisted Blueprint revision after fresh scoped approval."""

    APPROVALS = {
        "redeliver growth blueprint revision",
        "deliver growth blueprint revision",
        "share growth blueprint revision with client",
        "send growth blueprint revision to client",
    }
    GENERIC_APPROVALS = {"do that", "go ahead", "ok", "okay", "yes", "yes do that", "approve it"}

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()

    @property
    def mission_control_loader(self): return self.command_service.mission_control_loader
    @property
    def github_configured(self) -> bool: return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending = self.state.get("pending") if isinstance(self.state.get("pending"), dict) else None
        if pending and normalized in self.APPROVALS: return self._deliver(pending)
        if pending and normalized in self.GENERIC_APPROVALS: return self._ready(pending, generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "blueprint_revision_persisted_verified": return response
        revision = data.get("blueprint_revision") if isinstance(data.get("blueprint_revision"), dict) else {}
        revision_id = str(revision.get("revision_file_id") or "").strip()
        revision_url = str(revision.get("revision_file_url") or "").strip()
        original_id = str(revision.get("original_delivered_file_id") or revision.get("growth_blueprint_file_id") or "").strip()
        project_id = str(revision.get("delivery_project_record_id") or "").strip()
        if not revision_id or not revision_url or not original_id or not project_id or revision_id == original_id: return response
        if str(self.state.get("last_delivered_file_id") or "") == revision_id: return response
        pending = {
            "delivery_project_record_id": project_id,
            "lead_id": str(revision.get("lead_id") or ""),
            "contact": str(revision.get("contact") or ""),
            "company": str(revision.get("company") or ""),
            "original_delivered_file_id": original_id,
            "revision_file_id": revision_id,
            "revision_file_url": revision_url,
            "feedback_message_id": str(revision.get("feedback_message_id") or ""),
        }
        self.state["pending"] = pending; self._persist()
        return self._ready(pending, prefix=response.message + " ")

    def _ready(self, pending: dict[str, Any], *, generic: bool = False, prefix: str = "") -> CommandResponse:
        warning = "A generic approval is not enough to redeliver a revised client artifact. " if generic else ""
        label = str(pending.get("company") or pending.get("contact") or "the client")
        return CommandResponse(
            "blueprint_revision_delivery", "healthy",
            prefix + warning + f"The persisted Growth Blueprint revision for {label} is ready for client redelivery. Say 'redeliver Growth Blueprint revision' to approve sharing this exact new Drive artifact. The previously delivered file will remain untouched.",
            {"execution_status": "blueprint_revision_client_delivery_approval_required", "blueprint_revision": {**pending, "state": "awaiting_scoped_redelivery_approval"}, "approval_required": True, "external_action_taken": False},
        )

    def _deliver(self, pending: dict[str, Any]) -> CommandResponse:
        drive = self.dispatchers.get("Google Drive")
        if drive is None:
            return CommandResponse("blueprint_revision_delivery", "healthy", "Revision redelivery is approved, but no live Google Drive dispatcher is configured. Nothing has been shared.", {"execution_status": "blueprint_revision_client_delivery_dispatcher_unavailable", "external_action_taken": False})
        dispatch = {
            "eligible": True,
            "worker": "Google Drive",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_growth_blueprint_revision_client_redelivery",
            "instruction": "Make only the exact verified revision file client-deliverable. Do not overwrite, delete, unshare or modify permissions on the previously delivered Blueprint. Return verified mutation evidence for this exact revision file.",
            "expected_evidence": "verified Google Drive mutation proving the exact revision file became client-accessible",
            "payload": {
                "kind": "share_verified_growth_blueprint_revision",
                "delivery_project_record_id": pending["delivery_project_record_id"],
                "revision_file_id": pending["revision_file_id"],
                "revision_file_url": pending["revision_file_url"],
                "original_delivered_file_id": pending["original_delivered_file_id"],
            },
        }
        try: evidence = drive(dict(dispatch))
        except Exception as exc:
            return CommandResponse("blueprint_revision_delivery", "healthy", f"The approved revision redelivery failed: {exc}. Tony is not treating it as delivered.", {"execution_status": "blueprint_revision_client_delivery_failed", "external_action_taken": False})
        verification_evidence: Any = evidence
        if isinstance(evidence, dict):
            verification_evidence = dict(evidence)
            if not str(verification_evidence.get("url") or "").strip():
                returned_url = str(verification_evidence.get("delivery_url") or verification_evidence.get("share_url") or "").strip()
                if returned_url: verification_evidence["url"] = returned_url
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, verification_evidence)
        file_id = str(evidence.get("file_id") or evidence.get("document_id") or "").strip() if isinstance(evidence, dict) else ""
        delivery_url = str(evidence.get("delivery_url") or evidence.get("share_url") or evidence.get("url") or "").strip() if isinstance(evidence, dict) else ""
        externally_accessible = bool(evidence.get("externally_accessible") or evidence.get("shared")) if isinstance(evidence, dict) else False
        if not verified or file_id != pending["revision_file_id"] or not delivery_url or not externally_accessible:
            detail = reason if not verified else "missing exact revision-file delivery proof"
            return CommandResponse("blueprint_revision_delivery", "healthy", f"The revision redelivery evidence was insufficient ({detail}). Tony is not treating it as delivered.", {"execution_status": "blueprint_revision_client_delivery_unverified", "drive_revision_delivery_evidence": dict(evidence) if isinstance(evidence, dict) else {}, "external_action_taken": False})
        result = {**pending, "delivery_url": delivery_url, "state": "revision_client_delivery_verified"}
        self.state = {"pending": None, "last_delivered_file_id": pending["revision_file_id"], "last_delivered": result}; self._persist()
        return CommandResponse("blueprint_revision_delivery", "healthy", "Client redelivery of the verified Growth Blueprint revision is now evidenced. The previously delivered Blueprint remains untouched, and Tony has not inferred client acknowledgement or acceptance from the share action.", {"execution_status": "blueprint_revision_client_delivery_verified", "blueprint_revision_delivery": result, "drive_revision_delivery_evidence": dict(evidence), "external_action_taken": True})

    def _load(self) -> dict[str, Any]:
        try: value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError): return {"pending": None}
        return value if isinstance(value, dict) else {"pending": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True); temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp"); temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temp.replace(self.store_path)
