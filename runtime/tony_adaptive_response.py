from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyAdaptiveResponseCommandService:
    """Turn verified executive lessons into a safer next move."""

    _MARKERS = (
        "what should we try instead",
        "what do you recommend instead",
        "what would you do instead",
        "how should we adapt",
        "how do we adapt",
        "what should we change",
        "try something different",
    )
    _APPROVAL_MARKERS = (
        "go ahead",
        "go ahead with the redesign",
        "prepare the redesign",
        "prepare that",
        "do that",
        "let's do that",
        "lets do that",
        "try that",
    )
    _RETURN_MARKERS = (
        "review the redesign",
        "review what claude returned",
        "review claude's redesign",
        "review claudes redesign",
        "is the redesign good enough",
    )
    _FINAL_APPROVAL_MARKERS = (
        "approve it",
        "approve the redesign",
        "run the test",
        "go with that",
        "go with the recommendation",
        "let's test it",
        "lets test it",
        "go ahead with the test",
    )
    _REDESIGN_OUTCOMES = {"negative", "no_change"}
    _PROVISIONAL_OUTCOMES = {"mixed", "inconclusive"}

    def __init__(self, command_service, *, learning_store_path: Path | None = None) -> None:
        self.command_service = command_service
        self.learning_store_path = learning_store_path or Path(".runtime/executive-learning.json")
        self._pending_adaptation: dict[str, Any] | None = None
        self._pending_redesign_review: dict[str, Any] | None = None
        self._pending_reviewed_adaptation: dict[str, Any] | None = None

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        artefacts = tuple(item for item in objects if isinstance(item, dict))
        if self._pending_reviewed_adaptation and self._is_final_approval(lowered):
            return self._prepare_approved_adaptive_test()
        if self._pending_redesign_review and any(marker in lowered for marker in self._RETURN_MARKERS):
            return self._review_adaptation_return(artefacts)
        if self._pending_adaptation and self._is_adaptation_approval(lowered):
            return self._prepare_adaptation_handoff()
        if not any(marker in lowered for marker in self._MARKERS):
            return self.command_service.execute(command, artefacts)
        return self._adaptation_response()

    def _adaptation_response(self) -> CommandResponse:
        lesson = self._latest_relevant_lesson()
        if lesson is None:
            self._pending_adaptation = None
            return CommandResponse(
                "executive_adaptation",
                "healthy",
                "I do not yet have enough verified outcome evidence to justify changing the approach. I would get a clearer result signal first.",
                {"intent": "prepare_adaptive_approach", "adaptation_status": "insufficient_evidence", "execution_performed": False},
            )

        state = str(lesson.get("outcome_status") or "").casefold()
        key = str(lesson.get("priority_key") or "").strip()
        label = str(lesson.get("priority_label") or key or "this priority").strip()
        summary = str(lesson.get("outcome_summary") or "").strip()

        if state in self._PROVISIONAL_OUTCOMES:
            self._pending_adaptation = None
            return CommandResponse(
                "executive_adaptation",
                "attention",
                f"I would not change course yet on {label}. The last result was {state}, which is too weak a signal to justify a new approach. I recommend gathering one clearer matched outcome first; otherwise we risk learning the wrong lesson.",
                {
                    "intent": "prepare_adaptive_approach",
                    "adaptation_status": "gather_evidence_before_adaptation",
                    "priority": {"key": key, "label": label},
                    "prior_outcome": dict(lesson),
                    "recommended_next_step": "Gather one clearer matched business-outcome signal before changing the approach.",
                    "execution_performed": False,
                },
            )

        brief = {
            "worker": "Claude",
            "review_owner": "Tony",
            "priority": {"key": key, "label": label},
            "objective": f"Design a materially different next approach for {label} using the verified prior outcome as evidence.",
            "evidence": {"outcome_status": state, "outcome_summary": summary},
            "constraints": [
                "Do not repeat the previous approach unchanged.",
                "Change at least one material dimension: hypothesis, message, owner, timing or execution path.",
                "Prefer changing one major variable at a time so the next result remains learnable.",
                "Explain why each change responds to the recorded evidence rather than generic best practice.",
                "Return two or three options, recommend one, and define the signal that would prove or disprove it.",
            ],
            "approval_required": True,
            "execution_performed": False,
        }
        self._pending_adaptation = {
            "priority": {"key": key, "label": label},
            "prior_outcome": dict(lesson),
            "adaptation_brief": brief,
        }
        return CommandResponse(
            "executive_adaptation",
            "attention",
            f"I would change the approach rather than retry {label} unchanged. The last verified outcome was {state}{f': {summary}' if summary else ''}. My recommendation is to alter one meaningful variable at a time so the next result teaches us something. I have prepared a Claude-ready redesign brief; Tony retains review and approval is still required before execution.",
            {
                "intent": "prepare_adaptive_approach",
                "adaptation_status": "ready_for_adaptation_design",
                "priority": {"key": key, "label": label},
                "prior_outcome": dict(lesson),
                "adaptation_brief": brief,
                "execution_performed": False,
            },
        )

    def _prepare_adaptation_handoff(self) -> CommandResponse:
        assert self._pending_adaptation is not None
        pending = self._pending_adaptation
        brief = dict(pending["adaptation_brief"])
        handoff = {
            "worker": "Claude",
            "review_owner": "Tony",
            "task_type": "adaptive_redesign",
            "priority": dict(pending["priority"]),
            "brief": brief,
            "required_return": {
                "options": "two_or_three_materially_distinct_options",
                "recommendation": "one_preferred_option_with_reasoning",
                "changed_variable": "name_the_primary_variable_changed_from_the_previous_attempt",
                "success_signal": "define_the_business_signal_that_would_support_or_disprove_the_new_hypothesis",
            },
            "approval_boundary": "Tony must review the returned redesign before any external execution.",
            "execution_performed": False,
        }
        self._pending_adaptation = None
        self._pending_redesign_review = handoff
        label = str(pending["priority"].get("label") or "this priority")
        return CommandResponse(
            "executive_adaptation_handoff",
            "healthy",
            f"Agreed. I have prepared the adaptive redesign handoff for {label}. Claude should return distinct options, name the variable being changed and define the success signal. Tony remains responsible for review. Nothing has been executed externally yet.",
            {"intent": "delegate_adaptive_redesign", "adaptation_status": "worker_handoff_ready", "handoff": handoff, "execution_performed": False},
        )

    def _review_adaptation_return(self, artefacts: tuple[dict[str, Any], ...]) -> CommandResponse:
        if not artefacts:
            return CommandResponse(
                "executive_adaptation_review",
                "attention",
                "I cannot review the redesign yet because no returned worker artefact is attached. I will not treat the redesign as complete without evidence.",
                {"intent": "review_adaptive_redesign", "adaptation_status": "return_missing", "execution_performed": False},
            )

        artefact = artefacts[0]
        options = artefact.get("options")
        recommendation = str(artefact.get("recommendation") or "").strip()
        changed_variable = str(artefact.get("changed_variable") or "").strip()
        success_signal = str(artefact.get("success_signal") or "").strip()
        option_count = len(options) if isinstance(options, list) else 0
        gaps: list[str] = []
        if option_count < 2 or option_count > 3:
            gaps.append("two or three materially distinct options")
        if not recommendation:
            gaps.append("a preferred option with reasoning")
        if not changed_variable:
            gaps.append("the primary changed variable")
        if not success_signal:
            gaps.append("a measurable success signal")

        if gaps:
            self._pending_reviewed_adaptation = None
            return CommandResponse(
                "executive_adaptation_review",
                "attention",
                "The redesign is not ready for approval. I would send it back to Claude because it is missing " + ", ".join(gaps) + ". Nothing should execute yet.",
                {
                    "intent": "review_adaptive_redesign",
                    "adaptation_status": "revision_required",
                    "missing_requirements": gaps,
                    "execution_performed": False,
                },
            )

        pending = dict(self._pending_redesign_review or {})
        priority = pending.get("priority") if isinstance(pending.get("priority"), dict) else {}
        reviewed = {
            "priority": dict(priority),
            "options": list(options) if isinstance(options, list) else [],
            "recommendation": recommendation,
            "changed_variable": changed_variable,
            "success_signal": success_signal,
        }
        self._pending_reviewed_adaptation = reviewed
        self._pending_redesign_review = None
        return CommandResponse(
            "executive_adaptation_review",
            "healthy",
            f"The redesign is ready for approval. Claude returned {option_count} options, recommends one, changes {changed_variable}, and defines the success signal as: {success_signal}. I would approve the redesign for the next controlled test; nothing has executed externally yet.",
            {
                "intent": "review_adaptive_redesign",
                "adaptation_status": "ready_for_approval",
                "review": {
                    "option_count": option_count,
                    "recommendation": recommendation,
                    "changed_variable": changed_variable,
                    "success_signal": success_signal,
                },
                "approval_required": True,
                "execution_performed": False,
            },
        )

    def _prepare_approved_adaptive_test(self) -> CommandResponse:
        assert self._pending_reviewed_adaptation is not None
        reviewed = dict(self._pending_reviewed_adaptation)
        priority = reviewed.get("priority") if isinstance(reviewed.get("priority"), dict) else {}
        label = str(priority.get("label") or "this priority")
        handoff = {
            "task_type": "approved_adaptive_test",
            "execution_owner": "Tony",
            "priority": dict(priority),
            "approved_recommendation": reviewed.get("recommendation", ""),
            "changed_variable": reviewed.get("changed_variable", ""),
            "success_signal": reviewed.get("success_signal", ""),
            "options": list(reviewed.get("options") or []),
            "tool_resolution_required": True,
            "tool_selection_rule": "Choose the execution tool from the approved option and actual business action; do not invent a send, update or external execution path without evidence.",
            "completion_evidence_required": True,
            "outcome_evidence_required": True,
            "execution_performed": False,
        }
        self._pending_reviewed_adaptation = None
        return CommandResponse(
            "executive_adaptive_test_handoff",
            "healthy",
            f"Approved. I have converted the redesign for {label} into a controlled test handoff. The test must change {handoff['changed_variable']} and be judged against: {handoff['success_signal']}. I still need the actual execution tool to confirm completion before I call anything done.",
            {
                "intent": "execute_approved_adaptive_test",
                "adaptation_status": "approved_test_handoff_ready",
                "execution_handoff": handoff,
                "execution_performed": False,
                "external_action_taken": False,
            },
        )

    @classmethod
    def _is_adaptation_approval(cls, lowered: str) -> bool:
        cleaned = lowered.strip().rstrip(".!?")
        return any(marker == cleaned or cleaned.endswith(f" {marker}") for marker in cls._APPROVAL_MARKERS)

    @classmethod
    def _is_final_approval(cls, lowered: str) -> bool:
        cleaned = lowered.strip().rstrip(".!?")
        return any(marker == cleaned or cleaned.endswith(f" {marker}") for marker in cls._FINAL_APPROVAL_MARKERS)

    def _latest_relevant_lesson(self) -> dict[str, Any] | None:
        lessons = self._load_lessons()
        relevant = self._REDESIGN_OUTCOMES | self._PROVISIONAL_OUTCOMES
        for lesson in reversed(lessons):
            if str(lesson.get("outcome_status") or "").casefold() in relevant:
                return lesson
        return None

    def _load_lessons(self) -> list[dict[str, Any]]:
        if not self.learning_store_path.exists():
            return []
        try:
            raw = json.loads(self.learning_store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]
