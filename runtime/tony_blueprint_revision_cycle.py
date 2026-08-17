from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse
from runtime.tony_growth_blueprint_review import TonyGrowthBlueprintReviewCommandService


class TonyBlueprintRevisionCycleCommandService:
    """Turn verified client revision feedback into a reviewed internal revision.

    Client feedback is evidence, not permission to mutate the delivered artifact. This
    layer may autonomously ask Claude to prepare a bounded revision because preparation
    is reversible. Tony then quality-reviews the returned revision. Persistence and
    redelivery remain separate, explicitly approved downstream actions.
    """

    STATUS_MARKERS = {"revision status", "blueprint revision status", "what needs revising"}

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        if normalized in self.STATUS_MARKERS and isinstance(self.state.get("active"), dict):
            return self._status(self.state["active"])
        response = self.command_service.execute(command, objects)
        return self._capture(response)

    def _capture(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "blueprint_client_feedback_verified":
            return response
        feedback = data.get("blueprint_feedback") if isinstance(data.get("blueprint_feedback"), dict) else {}
        if feedback.get("revision_requested") is not True:
            return response
        evidence = data.get("gmail_feedback_evidence") if isinstance(data.get("gmail_feedback_evidence"), dict) else {}
        feedback_text = self._feedback_text(evidence)
        file_id = str(feedback.get("growth_blueprint_file_id") or "").strip()
        project_id = str(feedback.get("delivery_project_record_id") or "").strip()
        message_id = str(evidence.get("message_id") or evidence.get("gmail_message_id") or "").strip()
        if not feedback_text or not file_id or not project_id or not message_id:
            return CommandResponse("blueprint_revision_cycle", "healthy", response.message + " I cannot commission a revision until the verified feedback is tied to the exact delivered Blueprint and Gmail message.", {**data, "execution_status": "blueprint_revision_feedback_incomplete", "external_action_taken": False})
        active = {
            "delivery_project_record_id": project_id,
            "growth_blueprint_file_id": file_id,
            "delivery_url": str(feedback.get("delivery_url") or ""),
            "lead_id": str(feedback.get("lead_id") or ""),
            "contact": str(feedback.get("contact") or ""),
            "company": str(feedback.get("company") or ""),
            "feedback_message_id": message_id,
            "verified_feedback": feedback_text,
            "disposition": str(feedback.get("disposition") or "feedback_or_revision_request"),
        }
        self.state["active"] = active
        self._persist()
        return self._commission(active, base=response)

    def _commission(self, active: dict[str, Any], *, base: CommandResponse) -> CommandResponse:
        claude = self.dispatchers.get("Claude")
        if claude is None:
            return self._response(active, base, "blueprint_revision_dispatcher_unavailable", " The revision request is grounded, but no live Claude preparation dispatcher is configured. I have not altered the client artifact.")
        dispatch = self._dispatch(active)
        try:
            evidence = claude(dict(dispatch))
        except Exception as exc:
            return self._response(active, base, "blueprint_revision_preparation_failed", f" Claude revision preparation failed: {exc}. The delivered artifact remains unchanged.")
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return self._response(active, base, "blueprint_revision_preparation_unverified", f" Claude returned a possible revision, but it was not verified execution evidence ({reason}). The delivered artifact remains unchanged.", evidence)
        revision = self._revision_payload(evidence)
        review = TonyGrowthBlueprintReviewCommandService.review_blueprint(revision)
        active = {**active, "revision": revision, "tony_review": review}
        self.state["active"] = active
        self.state["last_revision"] = active
        self._persist()
        if review.get("decision") != "advance":
            return self._response(active, base, "blueprint_revision_requires_rework", " I prepared and reviewed an internal revision, but it is not decision-grade yet. I will not replace or redeliver the client artifact.", evidence)
        return self._response(active, base, "blueprint_revision_ready_for_approval", " I prepared and quality-reviewed an internal revision against the client's verified feedback. It is ready for a fresh approval before any Drive replacement or client redelivery. The current delivered artifact is unchanged.", evidence)

    @staticmethod
    def _dispatch(active: dict[str, Any]) -> dict[str, Any]:
        return {
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "worker": "Claude",
            "instruction": (
                "Prepare an internal revised Growth Blueprint working draft using only the exact verified client feedback and existing grounded Blueprint context. "
                "Address each requested change explicitly; preserve supported claims and source evidence; keep unknowns and hypotheses explicit. "
                "Return a complete revision suitable for Tony's Growth Blueprint quality review, including source_evidence, evidence_gaps, narratiive_fit, strategic_opportunity and recommendation. "
                "Do not write to Google Drive or Notion, do not contact the client, and do not claim the delivered artifact changed."
            ),
            "target": {"lead_id": active.get("lead_id", ""), "contact": active.get("contact", ""), "company": active.get("company", ""), "area": "delivery"},
            "execution_mode": "autonomous_prepare",
            "expected_evidence": "verified Claude preparation result containing a revised Growth Blueprint grounded in client feedback",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {
                "kind": "growth_blueprint_client_revision",
                "delivery_project_record_id": active.get("delivery_project_record_id", ""),
                "growth_blueprint_file_id": active.get("growth_blueprint_file_id", ""),
                "feedback_message_id": active.get("feedback_message_id", ""),
                "verified_client_feedback": active.get("verified_feedback", ""),
            },
        }

    @staticmethod
    def _revision_payload(evidence: dict[str, Any]) -> dict[str, Any]:
        for key in ("blueprint", "growth_blueprint", "result", "output"):
            value = evidence.get(key)
            if isinstance(value, dict):
                return dict(value)
        return dict(evidence)

    @staticmethod
    def _feedback_text(evidence: dict[str, Any]) -> str:
        for key in ("body", "content", "thread_content", "snippet", "summary", "result"):
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return ""

    def _status(self, active: dict[str, Any]) -> CommandResponse:
        review = active.get("tony_review") if isinstance(active.get("tony_review"), dict) else {}
        status = "blueprint_revision_ready_for_approval" if review.get("decision") == "advance" else "blueprint_revision_pending"
        return CommandResponse("blueprint_revision_cycle", "healthy", "The client revision cycle is grounded in verified feedback. " + ("The internal revision passed Tony's review and is awaiting fresh approval before any client artifact changes." if review.get("decision") == "advance" else "No client artifact has been changed."), {"execution_status": status, "blueprint_revision": dict(active), "external_action_taken": False})

    def _response(self, active: dict[str, Any], base: CommandResponse, status: str, suffix: str, evidence: dict[str, Any] | None = None) -> CommandResponse:
        data: dict[str, Any] = {"execution_status": status, "blueprint_revision": dict(active), "external_action_taken": False}
        if evidence is not None:
            data["claude_revision_evidence"] = dict(evidence)
        return CommandResponse("blueprint_revision_cycle", "healthy", base.message + suffix, data)

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"active": None, "last_revision": None}
        return value if isinstance(value, dict) else {"active": None, "last_revision": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.store_path)
