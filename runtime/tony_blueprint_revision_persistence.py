from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyBlueprintRevisionPersistenceCommandService:
    """Persist, redeliver and authoritatively record a reviewed Blueprint revision.

    Persistence, client redelivery and authoritative Notion bookkeeping remain three
    separate consequential writes. Each requires its own scoped approval and returned
    decision-grade execution evidence. None of these states imply client acknowledgement
    or acceptance.
    """

    APPROVALS = {"approve blueprint revision", "approve growth blueprint revision", "persist blueprint revision", "save blueprint revision"}
    REDELIVERY_APPROVALS = {"redeliver growth blueprint revision", "deliver growth blueprint revision", "share growth blueprint revision with client", "send growth blueprint revision to client"}
    NOTION_SYNC_APPROVALS = {
        "record growth blueprint revision delivery",
        "record blueprint revision delivery",
        "update notion with growth blueprint revision delivery",
        "mark growth blueprint revision delivered in notion",
        "mark the growth blueprint revision delivered in notion",
    }
    GENERIC_APPROVALS = {"do that", "go ahead", "ok", "okay", "yes", "yes do that", "approve it"}
    AUTHORITATIVE_REVISION_STATUS = "Growth Blueprint revision delivered"

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
        if normalized in self.NOTION_SYNC_APPROVALS and isinstance(self.state.get("notion_synced"), dict): return self._notion_sync_completed()
        if normalized in self.NOTION_SYNC_APPROVALS and isinstance(self.state.get("redelivered"), dict): return self._sync_redelivery_to_notion(self.state["redelivered"])
        if normalized in self.GENERIC_APPROVALS and isinstance(self.state.get("redelivered"), dict) and not self.state.get("notion_synced"):
            return self._notion_sync_ready(self.state["redelivered"], generic=True)
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
        self.state["active"] = dict(revision); self.state["persisted"] = None; self.state["redelivered"] = None; self.state["notion_synced"] = None; self._persist()
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
        if self.state.get("notion_synced"):
            return self._notion_sync_completed()
        if self.state.get("redelivered"):
            return self._notion_sync_ready(self.state["redelivered"])
        warning = "A generic approval is not enough to expose a revised client artifact. " if generic else ""
        data: dict[str, Any] = {"execution_status": "blueprint_revision_client_delivery_approval_required", "blueprint_revision": dict(persisted), "approval_required": True, "external_action_taken": False}
        if evidence is not None: data["drive_revision_evidence"] = dict(evidence)
        return CommandResponse("blueprint_revision_persistence", "healthy", prefix + warning + "A separate scoped approval is required before the revised Growth Blueprint becomes client-accessible. Say 'redeliver Growth Blueprint revision' to share only this exact new Drive artifact; the previously delivered file will remain untouched.", data)

    def _redeliver_revision(self, persisted: dict[str, Any]) -> CommandResponse:
        if self.state.get("redelivered"): return self._notion_sync_ready(self.state["redelivered"])
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
        return self._notion_sync_ready(result, prefix="Client redelivery of the verified Growth Blueprint revision is now evidenced. The previously delivered Blueprint remains untouched, and Tony has not inferred client acknowledgement or acceptance from the share action. ", evidence=evidence, external_action_taken=True)

    def _notion_sync_ready(self, redelivered: dict[str, Any], *, generic: bool = False, prefix: str = "", evidence: dict[str, Any] | None = None, external_action_taken: bool = False) -> CommandResponse:
        if self.state.get("notion_synced"):
            return self._notion_sync_completed()
        warning = "A generic approval is not enough to change the authoritative revision-delivery record. " if generic else ""
        data: dict[str, Any] = {
            "execution_status": "blueprint_revision_notion_sync_approval_required",
            "blueprint_revision_delivery": dict(redelivered),
            "approval_required": True,
            "external_action_taken": external_action_taken,
        }
        if evidence is not None: data["drive_revision_delivery_evidence"] = dict(evidence)
        return CommandResponse(
            "blueprint_revision_persistence",
            "healthy",
            prefix + warning + "The verified revision redelivery is ready to be recorded in authoritative Notion state. Say 'record Growth Blueprint revision delivery' to approve this exact bookkeeping update. Client acknowledgement and acceptance remain unverified.",
            data,
        )

    def _sync_redelivery_to_notion(self, redelivered: dict[str, Any]) -> CommandResponse:
        notion = self.dispatchers.get("Notion")
        if notion is None:
            return CommandResponse(
                "blueprint_revision_persistence",
                "healthy",
                "The revision redelivery is verified and the Notion update is approved, but no live Notion dispatcher is configured. The authoritative record has not been changed.",
                {"execution_status": "blueprint_revision_notion_dispatcher_unavailable", "blueprint_revision_delivery": dict(redelivered), "external_action_taken": False},
            )
        dispatch = {
            "worker": "Notion",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_growth_blueprint_revision_delivery_state_sync",
            "execution_truth": "not_dispatched",
            "target": {
                "delivery_project_record_id": redelivered.get("delivery_project_record_id", ""),
                "lead_id": redelivered.get("lead_id", ""),
                "contact": redelivered.get("contact", ""),
                "company": redelivered.get("company", ""),
                "area": "delivery",
            },
            "payload": {
                "kind": "growth_blueprint_revision_delivery_state_update",
                "delivery_project_record_id": redelivered.get("delivery_project_record_id", ""),
                "revision_file_id": redelivered.get("revision_file_id", ""),
                "original_delivered_file_id": redelivered.get("original_delivered_file_id", ""),
                "delivery_url": redelivered.get("delivery_url", ""),
                "feedback_message_id": redelivered.get("feedback_message_id", ""),
                "status": self.AUTHORITATIVE_REVISION_STATUS,
            },
            "instruction": "Update only the authoritative Notion delivery record to show that the exact verified Growth Blueprint revision artifact was redelivered. Preserve the new revision file identifier, prior delivered file identifier and verified delivery URL as evidence. Do not infer client receipt, acknowledgement, acceptance, satisfaction or project completion, and do not create any other client, calendar, email or delivery state.",
            "expected_evidence": "verified Notion mutation with record/page identifier and returned Growth Blueprint revision delivered status",
            "return_to": "Tony",
        }
        try: evidence = notion(dict(dispatch))
        except Exception as exc:
            return CommandResponse("blueprint_revision_persistence", "healthy", f"I attempted the approved Notion revision-delivery update, but it failed: {exc}. The authoritative record remains unverified.", {"execution_status": "blueprint_revision_notion_sync_failed", "blueprint_revision_delivery": dict(redelivered), "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        notion_id = str(evidence.get("record_id") or evidence.get("page_id") or "").strip() if isinstance(evidence, dict) else ""
        returned_status = str(evidence.get("status") or evidence.get("delivery_status") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not notion_id or returned_status.casefold() != self.AUTHORITATIVE_REVISION_STATUS.casefold():
            detail = reason if not verified else "missing authoritative record id or exact returned revision-delivery status"
            return CommandResponse("blueprint_revision_persistence", "healthy", f"The Notion revision-delivery evidence was insufficient ({detail}). Tony is not treating the authoritative record as updated.", {"execution_status": "blueprint_revision_notion_sync_unverified", "blueprint_revision_delivery": dict(redelivered), "notion_evidence": dict(evidence) if isinstance(evidence, dict) else {}, "external_action_taken": False})
        result = {**redelivered, "status": self.AUTHORITATIVE_REVISION_STATUS, "notion_record_id": notion_id}
        self.state["notion_synced"] = result; self._persist()
        return CommandResponse("blueprint_revision_persistence", "healthy", f"Confirmed. The authoritative Notion delivery record now shows {self.AUTHORITATIVE_REVISION_STATUS} for {redelivered.get('company') or redelivered.get('contact') or 'the client'}. This records verified revision redelivery only; client acknowledgement and acceptance remain unverified until separate evidence exists.", {"execution_status": "blueprint_revision_notion_sync_verified", "blueprint_revision_delivery_state": result, "notion_record_id": notion_id, "notion_evidence": dict(evidence), "external_action_taken": True})

    def _notion_sync_completed(self) -> CommandResponse:
        result = dict(self.state.get("notion_synced") or {})
        return CommandResponse("blueprint_revision_persistence", "healthy", "The verified Growth Blueprint revision redelivery is already recorded in authoritative Notion state; I will not repeat the update.", {"execution_status": "blueprint_revision_notion_sync_verified", "blueprint_revision_delivery_state": result, "notion_record_id": str(result.get("notion_record_id") or ""), "external_action_taken": False})

    def _response(self, active: dict[str, Any], status: str, message: str, evidence: dict[str, Any] | None = None) -> CommandResponse:
        data: dict[str, Any] = {"execution_status": status, "blueprint_revision": dict(active), "external_action_taken": False}
        if evidence is not None: data["drive_revision_evidence"] = dict(evidence)
        return CommandResponse("blueprint_revision_persistence", "healthy", message, data)

    def _load(self) -> dict[str, Any]:
        try: value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError): return {"active": None, "persisted": None, "redelivered": None, "notion_synced": None}
        if not isinstance(value, dict): return {"active": None, "persisted": None, "redelivered": None, "notion_synced": None}
        value.setdefault("redelivered", None); value.setdefault("notion_synced", None); return value

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True); temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp"); temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temp.replace(self.store_path)
