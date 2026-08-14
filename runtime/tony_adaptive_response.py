from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyAdaptiveResponseCommandService:
    """Turn verified executive lessons into a safer next move.

    The service reads the same persisted learning evidence as Tony's learning layer.
    It does not invent causality: negative/no-change evidence creates a bounded
    redesign brief, while mixed/inconclusive evidence causes Tony to ask for a
    clearer signal before changing course.
    """

    _MARKERS = (
        "what should we try instead",
        "what do you recommend instead",
        "what would you do instead",
        "how should we adapt",
        "how do we adapt",
        "what should we change",
        "try something different",
    )
    _REDESIGN_OUTCOMES = {"negative", "no_change"}
    _PROVISIONAL_OUTCOMES = {"mixed", "inconclusive"}

    def __init__(self, command_service, *, learning_store_path: Path | None = None) -> None:
        self.command_service = command_service
        self.learning_store_path = learning_store_path or Path(".runtime/executive-learning.json")

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        if not any(marker in lowered for marker in self._MARKERS):
            return self.command_service.execute(command, objects)
        return self._adaptation_response()

    def _adaptation_response(self) -> CommandResponse:
        lesson = self._latest_relevant_lesson()
        if lesson is None:
            return CommandResponse(
                "executive_adaptation",
                "healthy",
                "I do not yet have enough verified outcome evidence to justify changing the approach. I would get a clearer result signal first.",
                {
                    "intent": "prepare_adaptive_approach",
                    "adaptation_status": "insufficient_evidence",
                    "execution_performed": False,
                },
            )

        state = str(lesson.get("outcome_status") or "").casefold()
        key = str(lesson.get("priority_key") or "").strip()
        label = str(lesson.get("priority_label") or key or "this priority").strip()
        summary = str(lesson.get("outcome_summary") or "").strip()

        if state in self._PROVISIONAL_OUTCOMES:
            return CommandResponse(
                "executive_adaptation",
                "attention",
                (
                    f"I would not change course yet on {label}. The last result was {state}, which is too weak a signal to justify a new approach. "
                    "I recommend gathering one clearer matched outcome first; otherwise we risk learning the wrong lesson."
                ),
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
        return CommandResponse(
            "executive_adaptation",
            "attention",
            (
                f"I would change the approach rather than retry {label} unchanged. The last verified outcome was {state}"
                f"{f': {summary}' if summary else ''}. My recommendation is to alter one meaningful variable at a time so the next result teaches us something. "
                "I have prepared a Claude-ready redesign brief; Tony retains review and approval is still required before execution."
            ),
            {
                "intent": "prepare_adaptive_approach",
                "adaptation_status": "ready_for_adaptation_design",
                "priority": {"key": key, "label": label},
                "prior_outcome": dict(lesson),
                "adaptation_brief": brief,
                "execution_performed": False,
            },
        )

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
