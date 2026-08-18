from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintRevisionPersistenceCommandService:
    """Persist an approved reviewed Blueprint revision without overwriting the delivered artifact."""

    APPROVALS = {"approve blueprint revision", "approve growth blueprint revision", "persist blueprint revision", "save blueprint revision"}

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
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "blueprint_revision_ready_for_approval": return response
        revision = data.get("blueprint_revision") if isinstance(data.get("blueprint_revision"), dict) else {}
        review = revision.get("tony_review") if isinstance(revision.get("tony_review"), dict) else {}
        payload = revision.get("revision") if isinstance(revision.get("revision"), dict) else {}
        if review.get("status") != "ready_for_approval" or not payload or not str(revision.get("growth_blueprint_file_id") or "").strip(): return response
        self.state["active"] = dict(revision); self._persist()
        return CommandResponse("blueprint_revision_persistence", "healthy", response.message + " A fresh scoped approval is required before I persist this revision as a new Drive artifact. I will not overwrite the delivered Blueprint.", {**data, "execution_status": "blueprint_revision_persistence_approval_required", "external_action_taken": False})

    def _persist_revision(self, active: dict[str, Any]) -> CommandResponse:
        if self.state.get("persisted"):
            return CommandResponse("blueprint_revision_persistence", "healthy", "The approved revision has already been persisted; I will not create a duplicate.", {"execution_status": "blueprint_revision_persisted_verified", "blueprint_revision": dict(self.state["persisted"]), "external_action_taken": False})
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
        return CommandResponse("blueprint_revision_persistence", "healthy", "The approved revision is now persisted as a new verified Drive artifact. I did not overwrite or redeliver the existing client Blueprint. A separate client-redelivery approval is still required.", {"execution_status": "blueprint_revision_persisted_verified", "blueprint_revision": persisted, "drive_revision_evidence": dict(evidence), "external_action_taken": True})

    def _response(self, active: dict[str, Any], status: str, message: str, evidence: dict[str, Any] | None = None) -> CommandResponse:
        data: dict[str, Any] = {"execution_status": status, "blueprint_revision": dict(active), "external_action_taken": False}
        if evidence is not None: data["drive_revision_evidence"] = dict(evidence)
        return CommandResponse("blueprint_revision_persistence", "healthy", message, data)

    def _load(self) -> dict[str, Any]:
        try: value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError): return {"active": None, "persisted": None}
        return value if isinstance(value, dict) else {"active": None, "persisted": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True); temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp"); temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temp.replace(self.store_path)
