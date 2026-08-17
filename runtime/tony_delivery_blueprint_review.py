from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse
from runtime.tony_growth_blueprint_review import TonyGrowthBlueprintReviewer


class TonyDeliveryBlueprintReviewCommandService:
    """Review delivery evidence, prepare an internal Blueprint and persist only after scoped approval."""

    _KICKOFF_KEYS = {
        "known_facts": ("known_facts", "facts", "verified_facts"),
        "evidence_gaps": ("evidence_gaps", "gaps", "assumptions"),
        "research_plan": ("growth_blueprint_research_plan", "research_plan", "blueprint_research_plan"),
        "workplan": ("workplan", "delivery_workplan", "initial_workplan"),
    }
    _PERSIST_APPROVALS = {
        "approve growth blueprint",
        "approve the growth blueprint",
        "approve blueprint",
        "approve the blueprint",
        "save growth blueprint to drive",
        "save the growth blueprint to drive",
        "persist growth blueprint",
        "persist the growth blueprint",
    }
    _GENERIC_APPROVALS = {"do that", "go ahead", "ok", "okay", "yes", "yes do that", "approve it"}

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()
        self.reviewer = TonyGrowthBlueprintReviewer()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        ready = self._ready_blueprint()
        if ready and normalized in self._PERSIST_APPROVALS:
            return self._persist_approved_blueprint(ready)
        if ready and normalized in self._GENERIC_APPROVALS:
            return self._persistence_approval_required(ready, generic=True)
        response = self.command_service.execute(command, objects)
        return self._capture_and_prepare(response)

    def _ready_blueprint(self) -> dict[str, Any] | None:
        reviewed = self.state.get("last_reviewed") if isinstance(self.state.get("last_reviewed"), dict) else None
        if not reviewed or reviewed.get("state") != "ready_for_approval" or not reviewed.get("blueprint_prepared"):
            return None
        project_id = str(reviewed.get("delivery_project_record_id") or "").strip()
        persisted = set(str(item) for item in self.state.get("persisted", []) if item)
        return None if not project_id or project_id in persisted else dict(reviewed)

    def _capture_and_prepare(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "delivery_commission_verified":
            return response
        commissioning = data.get("delivery_commissioning") if isinstance(data.get("delivery_commissioning"), dict) else {}
        project_id = str(commissioning.get("delivery_project_record_id") or "").strip()
        work_product = commissioning.get("work_product") if isinstance(commissioning.get("work_product"), dict) else {}
        if not project_id or not work_product:
            return response

        completed = set(str(item) for item in self.state.get("completed", []) if item)
        if project_id in completed:
            return response

        kickoff_review = self._review_kickoff(work_product)
        context = {
            "delivery_project_record_id": project_id,
            "drive_folder_id": str(commissioning.get("drive_folder_id") or ""),
            "drive_folder_url": str(commissioning.get("drive_folder_url") or ""),
            "onboarding_record_id": str(commissioning.get("onboarding_record_id") or ""),
            "lead_id": str(commissioning.get("lead_id") or ""),
            "contact": str(commissioning.get("contact") or ""),
            "company": str(commissioning.get("company") or ""),
            "kickoff_evidence": dict(work_product),
            "kickoff_review": kickoff_review,
        }
        label = str(context.get("company") or context.get("contact") or "the client")
        if not kickoff_review["ready"]:
            self.state["pending"] = dict(context)
            self._persist()
            failed = ", ".join(kickoff_review["failed_checks"])
            return CommandResponse(
                "delivery_blueprint_review",
                "healthy",
                response.message + f" Tony reviewed the delivery kickoff for {label} and will not progress it yet. The kickoff is missing: {failed}. No Growth Blueprint draft has been commissioned.",
                {
                    "execution_status": "delivery_kickoff_revision_required",
                    "delivery_blueprint": {**context, "state": "kickoff_revision_required", "blueprint_prepared": False},
                    "external_action_taken": False,
                },
            )
        return self._prepare_blueprint(context, prefix=response.message + " ")

    def _prepare_blueprint(self, context: dict[str, Any], *, prefix: str = "") -> CommandResponse:
        claude = self.dispatchers.get("Claude")
        label = str(context.get("company") or context.get("contact") or "the client")
        if claude is None:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_blueprint_review",
                "healthy",
                prefix + f"Tony reviewed {label}'s delivery kickoff and it is strong enough to progress, but no live Claude dispatcher is configured. No Growth Blueprint draft has been prepared.",
                {
                    "execution_status": "delivery_blueprint_dispatcher_unavailable",
                    "delivery_blueprint": {**context, "state": "ready_for_internal_blueprint", "blueprint_prepared": False},
                    "external_action_taken": False,
                },
            )

        dispatch = {
            "worker": "Claude",
            "state": "ready_for_autonomous_dispatch",
            "eligible": True,
            "execution_mode": "autonomous_prepare",
            "execution_truth": "not_dispatched",
            "target": {
                "delivery_project_record_id": context["delivery_project_record_id"],
                "drive_folder_id": context.get("drive_folder_id", ""),
                "company": context.get("company", ""),
                "contact": context.get("contact", ""),
                "area": "delivery",
                "workspace_access": "reference_only",
            },
            "instruction": (
                "Prepare an internal working draft of the Narratiive Growth Blueprint for this onboarded client using only the verified delivery kickoff evidence supplied in this dispatch. "
                "Return structured evidence containing: growth_blueprint, sources or source_backed_evidence, evidence_gaps, narratiive_fit, strategic_growth_opportunity, and a recommendation that explicitly says advance, revise or stop. "
                "Treat unresolved evidence gaps as unknowns or hypotheses, never as facts. The draft must be substantial enough for Tony to review but is not client-facing and is not approved for delivery. "
                "Do not write to Google Drive or Notion, do not send any client communication, do not create calendar events, and do not invent objectives, audiences, research findings or commercial facts. "
                "Verified delivery kickoff evidence follows: " + json.dumps(context.get("kickoff_evidence", {}), sort_keys=True)
            ),
            "expected_evidence": "verified internal Growth Blueprint working draft with sources, explicit evidence gaps, Narratiive fit, strategic opportunity and advance/revise/stop recommendation",
            "return_to": "Tony",
        }
        try:
            evidence = claude(dict(dispatch))
        except Exception as exc:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_blueprint_review",
                "healthy",
                prefix + f"Tony approved the internal preparation step for {label}, but Claude did not return verified Growth Blueprint evidence: {exc}. Nothing has been persisted or sent.",
                {
                    "execution_status": "delivery_blueprint_dispatch_failed",
                    "delivery_blueprint": {**context, "state": "dispatch_attempted_unverified", "blueprint_prepared": False},
                    "external_action_taken": False,
                },
            )

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_blueprint_review",
                "healthy",
                prefix + f"Claude returned Growth Blueprint material for {label}, but the execution evidence was insufficient ({reason}). Tony is not treating the draft as prepared.",
                {
                    "execution_status": "delivery_blueprint_dispatch_unverified",
                    "delivery_blueprint": {**context, "state": "dispatch_attempted_unverified", "blueprint_prepared": False},
                    "claude_evidence": dict(evidence) if isinstance(evidence, dict) else {},
                    "external_action_taken": False,
                },
            )

        review = self.reviewer.review(evidence)
        completed = [str(item) for item in self.state.get("completed", []) if item]
        persisted = [str(item) for item in self.state.get("persisted", []) if item]
        project_id = str(context.get("delivery_project_record_id") or "")
        if review.status == "ready_for_approval" and project_id and project_id not in completed:
            completed.append(project_id)
        result = {
            **context,
            "state": review.status,
            "blueprint_prepared": True,
            "blueprint_evidence": dict(evidence),
            "tony_review": review.to_dict(),
        }
        self.state = {
            "pending": None if review.status == "ready_for_approval" else dict(result),
            "completed": completed[-100:],
            "persisted": persisted[-100:],
            "last_reviewed": result,
        }
        self._persist()

        if review.status == "ready_for_approval":
            message = (
                prefix
                + f"Claude returned an internal Growth Blueprint working draft for {label}, and Tony's quality gate passed. It is ready for your approval before anything is written to the client workspace. Say 'approve Growth Blueprint' to approve persistence of this exact reviewed draft to the verified Google Drive workspace. Nothing has been sent or persisted externally."
            )
            execution_status = "delivery_blueprint_ready_for_approval"
        elif review.status == "stop_recommended":
            message = (
                prefix
                + f"Claude returned the Growth Blueprint working draft for {label}, but Tony's review recommends stopping rather than progressing the current strategic direction. No client-facing output has been created."
            )
            execution_status = "delivery_blueprint_stop_recommended"
        else:
            failed = ", ".join(review.failed_checks) or "the stated revision"
            message = (
                prefix
                + f"Claude returned a Growth Blueprint working draft for {label}, but Tony's quality gate requires revision on: {failed}. No client-facing output has been created."
            )
            execution_status = "delivery_blueprint_revision_required"

        return CommandResponse(
            "delivery_blueprint_review",
            "healthy",
            message,
            {
                "execution_status": execution_status,
                "delivery_blueprint": result,
                "claude_evidence": dict(evidence),
                "tony_review": review.to_dict(),
                "approval_required": review.status == "ready_for_approval",
                "external_action_taken": False,
            },
        )

    def _persistence_approval_required(self, blueprint: dict[str, Any], *, generic: bool = False) -> CommandResponse:
        label = str(blueprint.get("company") or blueprint.get("contact") or "the client")
        prefix = "A generic approval is not enough to create an authoritative client delivery artifact. " if generic else ""
        return CommandResponse(
            "delivery_blueprint_persistence",
            "healthy",
            prefix + f"Tony's reviewed Growth Blueprint for {label} is ready. Say 'approve Growth Blueprint' to approve writing this exact reviewed draft into the verified Google Drive workspace. This approval does not send it to the client or change Notion or Calendar state.",
            {
                "execution_status": "delivery_blueprint_persistence_approval_required",
                "delivery_blueprint": {**blueprint, "persistence_state": "awaiting_scoped_approval"},
                "approval_required": True,
                "external_action_taken": False,
            },
        )

    def _persist_approved_blueprint(self, blueprint: dict[str, Any]) -> CommandResponse:
        drive = self.dispatchers.get("Google Drive")
        label = str(blueprint.get("company") or blueprint.get("contact") or "the client")
        folder_id = str(blueprint.get("drive_folder_id") or "").strip()
        evidence = blueprint.get("blueprint_evidence") if isinstance(blueprint.get("blueprint_evidence"), dict) else {}
        if not folder_id:
            return CommandResponse(
                "delivery_blueprint_persistence",
                "healthy",
                f"The Growth Blueprint for {label} passed Tony's review, but the verified client Drive folder identifier is missing. I will not write the artifact to an unverified location.",
                {"execution_status": "delivery_blueprint_drive_target_unverified", "external_action_taken": False},
            )
        if drive is None:
            return CommandResponse(
                "delivery_blueprint_persistence",
                "healthy",
                "Growth Blueprint persistence is approved, but no live Google Drive dispatcher is configured. I have not written any client artifact.",
                {
                    "execution_status": "delivery_blueprint_drive_dispatcher_unavailable",
                    "delivery_blueprint": {**blueprint, "persistence_state": "approved_pending_execution"},
                    "external_action_taken": False,
                },
            )

        filename = f"Growth Blueprint - {label}.md"
        dispatch = {
            "worker": "Google Drive",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "reviewed_growth_blueprint_to_verified_client_workspace",
            "execution_truth": "not_dispatched",
            "target": {
                "delivery_project_record_id": blueprint.get("delivery_project_record_id", ""),
                "drive_folder_id": folder_id,
                "company": blueprint.get("company", ""),
                "contact": blueprint.get("contact", ""),
                "area": "delivery",
            },
            "payload": {
                "kind": "reviewed_growth_blueprint_artifact",
                "parent_folder_id": folder_id,
                "folder": "01 Strategy",
                "filename": filename,
                "content": evidence.get("growth_blueprint") or evidence.get("work_product") or evidence,
                "source_evidence": evidence.get("sources") or evidence.get("source_backed_evidence") or [],
                "evidence_gaps": evidence.get("evidence_gaps") or [],
                "tony_review": blueprint.get("tony_review") or {},
            },
            "instruction": (
                "Write the exact Tony-reviewed Growth Blueprint artifact into the verified client's 01 Strategy Google Drive folder. "
                "Preserve the reviewed content and explicit evidence gaps. Do not share the file externally, email the client, update Notion, create calendar events, or modify other files."
            ),
            "expected_evidence": "verified Google Drive write with file identifier and file URL for the persisted Growth Blueprint artifact",
            "return_to": "Tony",
        }
        try:
            drive_evidence = drive(dict(dispatch))
        except Exception as exc:
            return CommandResponse(
                "delivery_blueprint_persistence",
                "healthy",
                f"The approved Growth Blueprint write failed: {exc}. Tony is not treating the artifact as persisted.",
                {"execution_status": "delivery_blueprint_drive_write_failed", "external_action_taken": False},
            )
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, drive_evidence)
        file_id = str(drive_evidence.get("file_id") or drive_evidence.get("document_id") or drive_evidence.get("source_id") or "").strip() if isinstance(drive_evidence, dict) else ""
        file_url = str(drive_evidence.get("file_url") or drive_evidence.get("web_view_link") or drive_evidence.get("url") or "").strip() if isinstance(drive_evidence, dict) else ""
        if not verified or not file_id or not file_url:
            detail = reason if not verified else "missing Drive file identifier or file URL"
            return CommandResponse(
                "delivery_blueprint_persistence",
                "healthy",
                f"The Growth Blueprint Drive evidence was insufficient ({detail}). Tony is not treating the artifact as persisted.",
                {
                    "execution_status": "delivery_blueprint_drive_write_unverified",
                    "drive_evidence": dict(drive_evidence) if isinstance(drive_evidence, dict) else {},
                    "external_action_taken": False,
                },
            )

        project_id = str(blueprint.get("delivery_project_record_id") or "")
        persisted = [str(item) for item in self.state.get("persisted", []) if item]
        if project_id and project_id not in persisted:
            persisted.append(project_id)
        artifact = {
            **blueprint,
            "persistence_state": "persisted_verified",
            "growth_blueprint_file_id": file_id,
            "growth_blueprint_file_url": file_url,
            "growth_blueprint_filename": filename,
        }
        self.state["persisted"] = persisted[-100:]
        self.state["last_persisted"] = artifact
        self._persist()
        return CommandResponse(
            "delivery_blueprint_persistence",
            "healthy",
            f"The reviewed Growth Blueprint for {label} is now verified as persisted in the client Google Drive workspace. It has not been shared or sent to the client, and no Notion or Calendar state was changed.",
            {
                "execution_status": "delivery_blueprint_persisted_verified",
                "delivery_blueprint": artifact,
                "drive_evidence": dict(drive_evidence),
                "approval_required": False,
                "external_action_taken": True,
            },
        )

    @classmethod
    def _review_kickoff(cls, evidence: dict[str, Any]) -> dict[str, Any]:
        checks: dict[str, bool] = {}
        for check, keys in cls._KICKOFF_KEYS.items():
            checks[check] = any(cls._meaningful(evidence.get(key)) for key in keys)
        failed = [name for name, passed in checks.items() if not passed]
        return {"ready": not failed, "checks": checks, "failed_checks": failed, "judgement_owner": "Tony"}

    @staticmethod
    def _meaningful(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed": [], "persisted": []}
        if not isinstance(value, dict):
            return {"pending": None, "completed": [], "persisted": []}
        value.setdefault("persisted", [])
        return value

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.store_path)
