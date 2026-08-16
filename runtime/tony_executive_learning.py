from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyExecutiveLearningCommandService:
    """Turn verified outcomes into reusable executive learning.

    This layer records outcome lessons and prevents Tony from blindly preparing the
    same priority action after evidence says the previous approach failed or produced
    no change. It remains conservative: lessons are scoped to the recorded priority
    key and never imply broader causality than the evidence supports.
    """

    _LEARNING_MARKERS = (
        "what did we learn",
        "what have we learned",
        "what did you learn",
        "what have you learned",
        "what should we learn from that",
        "what should we learn",
    )
    _BLOCKING_OUTCOMES = {"negative", "no_change"}
    _PROVISIONAL_OUTCOMES = {"mixed", "inconclusive"}
    _SCALE_READY_POSITIVE_RUN = 4

    def __init__(self, command_service, *, store_path: Path | None = None, max_lessons: int = 50) -> None:
        self.command_service = command_service
        self.store_path = store_path or Path(".runtime/executive-learning.json")
        self.max_lessons = max(1, max_lessons)
        self._lessons = self._load_lessons()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        materialized = tuple(objects)

        if any(marker in lowered for marker in self._LEARNING_MARKERS):
            return self._learning_summary()

        response = self.command_service.execute(command, materialized)

        if response.command == "executive_outcome_review":
            self._capture_outcome_lesson(response)
            return response

        if response.command == "agency_focus_action":
            return self._apply_learning_guard(response)

        return response

    def _capture_outcome_lesson(self, response: CommandResponse) -> None:
        data = response.data if isinstance(response.data, dict) else {}
        if not bool(data.get("accepted")):
            return
        outcome = data.get("outcome")
        if not isinstance(outcome, dict):
            return
        state = str(outcome.get("outcome_status") or "").strip().casefold()
        priority = outcome.get("priority") if isinstance(outcome.get("priority"), dict) else {}
        key = str(priority.get("key") or "").strip()
        if not key or not state:
            return

        lesson = {
            "priority_key": key,
            "priority_label": str(priority.get("label") or key).strip(),
            "outcome_status": state,
            "outcome_summary": str(outcome.get("summary") or "").strip(),
            "recorded_at": str(outcome.get("recorded_at") or datetime.now(timezone.utc).isoformat()),
            "guidance": self._guidance_for(state),
        }
        self._lessons.append(lesson)
        self._lessons = self._lessons[-self.max_lessons :]
        self._persist_lessons()

    def _apply_learning_guard(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        priority = data.get("priority") if isinstance(data.get("priority"), dict) else {}
        key = str(priority.get("key") or "").strip()
        if not key:
            return response

        lesson = self._latest_lesson_for(key)
        if lesson is None:
            return response

        state = str(lesson.get("outcome_status") or "").casefold()
        if state in self._BLOCKING_OUTCOMES:
            guidance = str(lesson.get("guidance") or self._guidance_for(state))
            data["learning_guard"] = {
                "status": "adapt_before_repeat",
                "prior_outcome": state,
                "lesson": dict(lesson),
            }
            data["execution_status"] = "requires_adaptation"
            data["external_action_taken"] = False
            message = (
                f"{response.message} One important caveat: the last verified outcome for this same priority was {state}. "
                f"{guidance} I would adapt the approach before handing the same move off again."
            )
            return CommandResponse(response.command, "attention", message, data)

        if state in self._PROVISIONAL_OUTCOMES:
            guidance = str(lesson.get("guidance") or self._guidance_for(state))
            data["learning_guard"] = {
                "status": "provisional_evidence",
                "prior_outcome": state,
                "lesson": dict(lesson),
            }
            message = f"{response.message} Previous evidence on this priority was {state}; {guidance}"
            return CommandResponse(response.command, response.status, message, data)

        if state == "positive":
            guidance = str(lesson.get("guidance") or self._guidance_for(state))
            positive_run = self._consecutive_positive_count(key)
            if positive_run >= self._SCALE_READY_POSITIVE_RUN:
                scale_guardrails = {
                    "mode": "measured_incremental_scale",
                    "exposure_step": "one_increment_only",
                    "preserve_working_elements": True,
                    "preserve_success_signal": True,
                    "review_checkpoint": "after_next_matched_outcome",
                    "stop_or_adapt_condition": "material weakening, negative outcome, or no_change outcome",
                    "approval_required_before_external_scale": True,
                    "external_action_taken": False,
                }
                data["learning_guard"] = {
                    "status": "measured_scale_candidate",
                    "prior_outcome": state,
                    "positive_evidence_count": positive_run,
                    "recommended_scale_mode": "incremental",
                    "preserve_success_signal": True,
                    "scale_guardrails": scale_guardrails,
                    "lesson": dict(lesson),
                }
                data["scale_guardrails"] = dict(scale_guardrails)
                data["external_action_taken"] = False
                message = (
                    f"{response.message} We now have {positive_run} consecutive verified positive outcomes for this same priority. "
                    "That is enough evidence to treat this as a measured scale candidate rather than another simple repeat. "
                    "I would increase exposure by one controlled increment only, preserve the elements that appear to be working and keep the same success signal. "
                    "We should review the next matched outcome before increasing exposure again, and stop or adapt if the effect materially weakens. "
                    "Any external scale-up still requires explicit approval."
                )
                return CommandResponse(response.command, response.status, message, data)

            if positive_run >= 2:
                data["learning_guard"] = {
                    "status": "positive_pattern_emerging",
                    "prior_outcome": state,
                    "positive_evidence_count": positive_run,
                    "lesson": dict(lesson),
                }
                message = (
                    f"{response.message} We now have {positive_run} consecutive verified positive outcomes for this same priority. "
                    "That is an emerging pattern rather than a one-off, so I would preserve the elements that appear to be working "
                    "and run a controlled repeat before materially scaling the approach."
                )
                return CommandResponse(response.command, response.status, message, data)

            data["learning_guard"] = {
                "status": "evidence_supported_repeat",
                "prior_outcome": state,
                "positive_evidence_count": positive_run,
                "lesson": dict(lesson),
            }
            message = (
                f"{response.message} The last verified outcome for this same priority was positive. "
                f"{guidance} I would preserve the elements that appear to have worked while still treating this as scoped evidence, not a guarantee."
            )
            return CommandResponse(response.command, response.status, message, data)

        return response

    def _learning_summary(self) -> CommandResponse:
        if not self._lessons:
            return CommandResponse(
                command="executive_learning",
                status="healthy",
                message="I do not yet have enough verified outcome evidence to claim an executive learning pattern.",
                data={"intent": "summarise_executive_learning", "lessons": []},
            )

        recent = self._lessons[-5:]
        lines = ["The evidence-backed lessons I am carrying forward are:"]
        for lesson in reversed(recent):
            label = str(lesson.get("priority_label") or lesson.get("priority_key") or "a prior action")
            state = str(lesson.get("outcome_status") or "inconclusive")
            summary = str(lesson.get("outcome_summary") or "").strip()
            guidance = str(lesson.get("guidance") or "").strip()
            detail = f" — {summary}" if summary else ""
            lines.append(f"- {label}: {state}{detail}. {guidance}")
        lines.append("I will use these as scoped evidence, not as universal rules; new evidence can overturn them.")
        return CommandResponse(
            command="executive_learning",
            status="healthy",
            message="\n".join(lines),
            data={"intent": "summarise_executive_learning", "lessons": [dict(item) for item in recent]},
        )

    def _latest_lesson_for(self, priority_key: str) -> dict[str, Any] | None:
        for lesson in reversed(self._lessons):
            if str(lesson.get("priority_key") or "") == priority_key:
                return lesson
        return None

    def _consecutive_positive_count(self, priority_key: str) -> int:
        count = 0
        for lesson in reversed(self._lessons):
            if str(lesson.get("priority_key") or "") != priority_key:
                continue
            if str(lesson.get("outcome_status") or "").casefold() != "positive":
                break
            count += 1
        return count

    @staticmethod
    def _guidance_for(state: str) -> str:
        if state == "positive":
            return "Preserve the evidence-backed elements that worked, but do not assume the result generalises beyond this case."
        if state in {"negative", "no_change"}:
            return "Do not repeat the same approach unchanged; alter the hypothesis, message, owner or execution path before another attempt."
        return "Keep the judgement provisional and gather stronger evidence before scaling or abandoning the approach."

    def _load_lessons(self) -> list[dict[str, Any]]:
        if not self.store_path.exists():
            return []
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)][-self.max_lessons :]

    def _persist_lessons(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._lessons, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)
