from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintRevisionPersistenceCommandService:
    """Persist an approved reviewed Blueprint revision and redeliver it only after a second scoped approval."""

    APPROVALS = {"approve blueprint revision", "approve growth blueprint revision", "persist blueprint revision", "save blueprint revision"}
    REDELIVERY_APPROVALS = {"redeliver growth blueprint revision", "deliver growth blueprint revision", "share growth blueprint revision with client", "send growth blueprint revision to client"}
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
        if normalized in self.APPROVALS and isinstance(self.state.get("active"), dict): return self._persist_revision(self.state["active"])
        if normalized in self.REDELIVERY_APPROVALS and isinstance(self.state.get("persisted"), dict): return self._redeliver_revision(self.state["persisted"])
        if normalized in self.GENERIC_APPROVALS and isinstance(self.state.get("persisted"), dict) and not self.state.get("redelivered"):
            return self._redelivery_ready(self.state["persisted"], generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "blueprint_revision_ready_for_approval": return response
        revision = data.get("blueprint_revision") if isinstance(data.get("blueprint_revision"), dict) else {}
        review = revision.get("tony_review") if isinstance(revision.get("tony_review"), dict) else {}
        payload = revision.get("revision") if isinstance(revision.get("revision"), dict) else {}
        if review.get("status") != "ready_for_approval" or not payload or not str(revision.get("growth_blueprint_file_id") or "").strip(): return response
        self.state["active"] = dict(revision); self.state["persisted"] = None; self.state["redelivered"] = None; self._persist()
        return CommandResponse("blueprint_revision_persistence", "healthy", response.message + " A fresh scoped approval is required before I persist this revision as a new Drive artifact. I will not overwrite the delivered Blueprint.", {**data, "execution_status": "blueprint_revision_persistence_approval_required", "external_action_taken": False})

    def _persist_revision(self, active: dict[str, Any]) -> CommandResponse:
        if self.state.get("persisted"):
            return self._redelivery_ready(self.state["persisted"])
        drive = self.dispatchers.get("Google Drive")
        if drive is None: return self._response(active, "blueprint_revision_drive_dispatcher_unavailable", "The revision is approved, but no live Google Drive dispatcher is configured. The delivered Blueprint remains unchanged.")
        original_id = str(active.get("growth_blueprint_file_id") or "").strip()
        dispatch = {"eligible": True, "state": "approved_pending_execution", "worker": "Google Drive", "instruction": "Create a new internal Growth Blueprint revision artifact alongside the existing delivered Blueprint. Do not overwrite, delete, share or change permissions on the delivered file. Return verified mutation evidence with a new file_id and url.", "execution_mode": "approval_gated_write", "approval_granted": True, "approval_scope": "reviewed_growth_blueprint_revision_new_version", "expected_evidence": "verified Google Drive mutation evidence for a newly created revision file", "payload": {"kind": "growth_blueprint_revision", "delivery_project_record_id": active.get("delivery_project_record_id", ""), "original_delivered_file_id": original_id, "feedback_message_id": active.get("feedback_message_id", ""), "filename": f"Growth Blueprint - {active.get('company') or 'Client'} - Revision.md", "content": active.get("revision", {}), "tony_review": active.get("tony_review", {})}}
        try: evidence = drive(dict(dispatch))
        except Exception as exc: return self._response(active, "blueprint_revision_drive_write_failed", f"Google Drive revision persistence failed: {exc}. The delivered Blueprint remains unchanged.")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        new_id = str(evidence.get("file_id") or "").strip() if isinstance(evidence, dict) else ""; url = str(evidence.get("url") or evidence.get("file_url") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not new_id or not url or new_id == original_id: return self._response(active, "blueprint_revision_drive_write_unverified", f"Drive did not return decision-grade evidence for a distinct revision artifact ({reason if not verified else 'new file identity required'}). The delivered Blueprint remains unchanged.", evidence if isinstance(evidence, dict) else None)
        persisted = {**active, "revision_file_id": new_id, "revision_file_url": url, "original_delivered_file_id": original_id}; self.state["persisted"] = persisted; self.state["active"] = None; self._persist()
        return self._redelivery_ready(persisted, prefix="The approved revision is now persisted as a new verified Drive artifact. I did not overwrite or redeliver the existing client Blueprint. ", evidence=evidence)

    def _redelivery_ready(self, persisted: dict[str, Any], *, generic: bool = False, prefix: str = "", evidence: dict[str, Any] | None = None) -> CommandResponse:
        if self.state.get("redelivered"):
            result = dict(self.state["redelivered"])
            return CommandResponse("blueprint_revision_persistence", "healthy", "The verified Blueprint revision has already been redelivered; I will not repeat the share action.", {"execution_status": "blueprint_revision_client_delivery_verified", "blueprint_revision_delivery": result, "external_action_taken": False})
        warning = "A generic approval is not enough to expose a revised client artifact. " if generic else ""
        data: dict[str, Any] = {"execution_status": "blueprint_revision_client_delivery_approval_required", "blueprint_revision": dict(persisted), "approval_required": True, "external_action_taken": False}
        if evidence is not None: data["drive_revision_evidence"] = dict(evidence)
        return CommandResponse("blueprint_revision_persistence", "healthy", prefix + warning + "A separate scoped approval is required before the revised Growth Blueprint becomes client-accessible. Say 'redeliver Growth Blueprint revision' to share only this exact new Drive artifact; the previously delivered file will remain untouched.", data)

    def _redeliver_revision(self, persisted: dict[str, Any]) -> CommandResponse:
        if self.state.get("redelivered"): return self._redelivery_ready(persisted)
        drive = self.dispatchers.get("Google Drive")
        if drive is None:
            return CommandResponse("blueprint_revision_persistence", "healthy", "Revision redelivery is approved, but no live Google Drive dispatcher is configured. Nothing has been shared.", {"execution_status": "blueprint_revision_client_delivery_dispatcher_unavailable", "blueprint_revision": dict(persisted), "external_action_taken": False})
        revision_id = str(persisted.get("revision_file_id") or "").strip(); original_id = str(persisted.get("original_delivered_file_id") or "").strip()
        dispatch = {"eligible": True, "state": "approved_pending_execution", "worker": "Google Drive", "instruction": "Make only the exact verified Growth Blueprint revision file client-deliverable. Do not overwrite, delete, unshare or modify permissions on the previously delivered Blueprint. Return verified mutation evidence for this exact revision file.", "execution_mode": "approval_gated_write", "approval_granted": True, "approval_scope": "verified_growth_blueprint_revision_client_redelivery", "expected_evidence": "verified Google Drive mutation proving the exact revision file became client-accessible", "payload": {"kind": "share_verified_growth_blueprint_revision", "delivery_project_record_id": persisted.get("delivery_project_record_id", ""), "revision_file_id": revision_id, "revision_file_url": persisted.get("revision_file_url", ""), "original_delivered_file_id": original_id}}
        try: evidence = drive(dict(dispatch))
        except Exception as exc:
            return CommandResponse("blueprint_revision_persistence", "healthy", f"The approved revision redelivery failed: {exc}. Tony is not treating it as delivered.", {"execution_status": "blueprint_revision_client_delivery_failed", "blueprint_revision": dict(persisted), "external_action_taken": False})
        verification_evidence: Any = evidence
        if isinstance(evidence, dict):
            verification_evidence = dict(evidence)
            if not str(verification_evidence.get("url") or "").strip():
                returned_url = str(verification_evidence.get("delivery_url") or verification_evidence.get("share_url") or "").strip()
                if returned_url: verification_evidence["url"] = returned_url
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, verification_evidence)
        file_id = str(evidence.get("file_id") or evidence.get("document_id") or "").strip() if isinstance(evidence, dict) else ""; delivery_url = str(evidence.get("delivery_url") or evidence.get("share_url") or evidence.get("url") or "").strip() if isinstance(evidence, dict) else ""; externally_accessible = bool(evidence.get("externally_accessible") or evidence.get("shared")) if isinstance(evidence, dict) else False
        if not verified or file_id != revision_id or not delivery_url or not externally_accessible:
            detail = reason if not verified else "missing exact revision-file delivery proof"
            return CommandResponse("blueprint_revision_persistence", "healthy", f"The revision redelivery evidence was insufficient ({detail}). Tony is not treating it as delivered.", {"execution_status": "blueprint_revision_client_delivery_unverified", "blueprint_revision": dict(persisted), "drive_revision_delivery_evidence": dict(evidence) if isinstance(evidence, dict) else {}, "external_action_taken": False})
        result = {**persisted, "delivery_url": delivery_url, "state": "revision_client_delivery_verified"}; self.state["redelivered"] = result; self._persist()
        return CommandResponse("blueprint_revision_persistence", "healthy", "Client redelivery of the verified Growth Blueprint revision is now evidenced. The previously delivered Blueprint remains untouched, and Tony has not inferred client acknowledgement or acceptance from the share action.", {"execution_status": "blueprint_revision_client_delivery_verified", "blueprint_revision_delivery": result, "drive_revision_delivery_evidence": dict(evidence), "external_action_taken": True})

    def _response(self, active: dict[str, Any], status: str, message: str, evidence: dict[str, Any] | None = None) -> CommandResponse:
        data: dict[str, Any] = {"execution_status": status, "blueprint_revision": dict(active), "external_action_taken": False}
        if evidence is not None: data["drive_revision_evidence"] = dict(evidence)
        return CommandResponse("blueprint_revision_persistence", "healthy", message, data)

    def _load(self) -> dict[str, Any]:
        try: value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError): return {"active": None, "persisted": None, "redelivered": None}
        if not isinstance(value, dict): return {"active": None, "persisted": None, "redelivered": None}
        value.setdefault("redelivered", None); return value

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True); temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp"); temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temp.replace(self.store_path)
