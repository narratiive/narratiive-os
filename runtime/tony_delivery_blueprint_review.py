from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse
from runtime.tony_growth_blueprint_review import TonyGrowthBlueprintReviewer


class TonyDeliveryBlueprintReviewCommandService:
    """Review verified delivery kickoff evidence and prepare a bounded internal Growth Blueprint draft."""

    _KICKOFF_KEYS = {
        "known_facts": ("known_facts", "facts", "verified_facts"),
        "evidence_gaps": ("evidence_gaps", "gaps", "assumptions"),
        "research_plan": ("growth_blueprint_research_plan", "research_plan", "blueprint_research_plan"),
        "workplan": ("workplan", "delivery_workplan", "initial_workplan"),
    }

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
        response = self.command_service.execute(command, objects)
        return self._capture_and_prepare(response)

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
        self.state = {"pending": None if review.status == "ready_for_approval" else dict(result), "completed": completed[-100:], "last_reviewed": result}
        self._persist()

        if review.status == "ready_for_approval":
            message = (
                prefix
                + f"Claude returned an internal Growth Blueprint working draft for {label}, and Tony's quality gate passed. It is ready for your approval before any client-facing deliverable is created or anything is written to the client workspace. Nothing has been sent or persisted externally."
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
            return {"pending": None, "completed": []}
        return value if isinstance(value, dict) else {"pending": None, "completed": []}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.store_path)
