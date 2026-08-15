from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.tony_command_service import CommandResponse


class TonyOutcomeAccountabilityCommandService:
    """Separate verified execution from verified business outcome.

    Tony should never confuse "the worker completed the step" with "the step worked".
    This layer remembers the most recent completed executive action, accepts explicit
    outcome evidence, and surfaces an outcome check when evidence remains absent.
    """

    _OUTCOME_COMMANDS = {"outcome_result", "record_outcome", "outcome_evidence"}
    _OUTCOME_MARKERS = (
        "did that work",
        "did it work",
        "what was the outcome",
        "what's the outcome",
        "whats the outcome",
        "was it successful",
        "did that achieve anything",
        "what happened as a result",
    )
    _OUTCOME_STATES = {"positive", "negative", "mixed", "no_change", "inconclusive"}

    def __init__(
        self,
        command_service,
        *,
        store_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        check_after: timedelta = timedelta(hours=24),
    ) -> None:
        self.command_service = command_service
        self.store_path = store_path or Path(".runtime/executive-outcomes.json")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.check_after = check_after
        state = self._load_state()
        self._awaiting_outcome: dict[str, Any] | None = state["awaiting_outcome"]
        self._last_outcome: dict[str, Any] | None = state["last_outcome"]

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
        name = lowered.split(" ", 1)[0].lstrip("/") if lowered else ""
        materialized = tuple(objects)

        if name in self._OUTCOME_COMMANDS:
            return self._record_outcome(materialized)

        if any(marker in lowered for marker in self._OUTCOME_MARKERS):
            return self._outcome_status()

        response = self.command_service.execute(command, materialized)
        if response.command == "agency_focus_action_result":
            response = self._capture_verified_completion(response)
        if response.command in {"morning", "evening"}:
            response = self._augment_brief_with_outcome_watch(response)
        return response

    def _capture_verified_completion(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if not bool(data.get("accepted")) or data.get("execution_status") != "completed_verified":
            return response
        completed = data.get("completed_action")
        if not isinstance(completed, dict):
            return response

        action_id = str(completed.get("action_id") or "").strip()
        if not action_id:
            return response

        success_signal = str(completed.get("success_signal") or "").strip()
        changed_variable = str(completed.get("changed_variable") or "").strip()
        adaptive_test = bool(completed.get("adaptive_test"))
        measurement_request = None
        if adaptive_test and success_signal:
            measurement_request = {
                "action_id": action_id,
                "measure_against": success_signal,
                "changed_variable": changed_variable,
                "evidence_required": True,
                "outcome_status_required": True,
            }

        self._awaiting_outcome = {
            "action_id": action_id,
            "priority": dict(completed.get("priority") or {}) if isinstance(completed.get("priority"), dict) else {},
            "completed_at": str(completed.get("completed_at") or self._now_utc().isoformat()),
            "completion_evidence": completed.get("completion_evidence"),
            "result_summary": str(completed.get("result_summary") or "").strip(),
            "adaptive_test": adaptive_test,
            "changed_variable": changed_variable,
            "success_signal": success_signal,
            "measurement_request": measurement_request,
        }
        self._persist_state()
        data["business_outcome_status"] = "unverified"
        if measurement_request:
            data["outcome_measurement_handoff"] = dict(measurement_request)
            message = (
                f"{response.message} Execution is verified; the business outcome is not yet verified. "
                f"I will judge this test against the agreed success signal: {success_signal}. "
                "I still need outcome evidence before I can call the test effective."
            )
        else:
            message = (
                f"{response.message} Execution is verified; the business outcome is not yet verified. "
                "I will keep those two claims separate until outcome evidence exists."
            )
        return CommandResponse(response.command, response.status, message, data)

    def _record_outcome(self, objects: tuple[dict[str, Any], ...]) -> CommandResponse:
        if not self._awaiting_outcome:
            return self._reject_outcome("There is no completed executive action currently awaiting outcome evidence.")

        result = self._extract_outcome(objects)
        if result is None:
            return self._reject_outcome("No structured outcome evidence was supplied.")

        expected_id = str(self._awaiting_outcome.get("action_id") or "")
        supplied_id = str(result.get("action_id") or result.get("executive_action_id") or "").strip()
        if not supplied_id or supplied_id != expected_id:
            return self._reject_outcome("The outcome evidence does not match the completed action being assessed.")

        state = str(result.get("outcome_status") or result.get("outcome") or "").strip().casefold()
        if state not in self._OUTCOME_STATES:
            return self._reject_outcome("Outcome status must be positive, negative, mixed, no_change or inconclusive.")

        evidence = result.get("evidence")
        if evidence is None or evidence == "" or evidence == [] or evidence == {}:
            return self._reject_outcome("Outcome evidence is required before I can judge whether the action worked.")

        outcome = {
            "action_id": expected_id,
            "outcome_status": state,
            "evidence": evidence,
            "summary": str(result.get("summary") or "").strip(),
            "recorded_at": self._now_utc().isoformat(),
            "priority": dict(self._awaiting_outcome.get("priority") or {}),
            "adaptive_test": bool(self._awaiting_outcome.get("adaptive_test")),
            "changed_variable": str(self._awaiting_outcome.get("changed_variable") or ""),
            "success_signal": str(self._awaiting_outcome.get("success_signal") or ""),
        }
        self._last_outcome = outcome
        self._awaiting_outcome = None
        self._persist_state()

        label = str(outcome["priority"].get("label") or "the completed action")
        if state == "positive":
            judgement = "The evidence supports a positive business outcome. I would preserve what worked and reassess the next live priority before scaling it further."
            status = "healthy"
        elif state in {"negative", "no_change"}:
            judgement = "The evidence does not support the intended business outcome. I would not repeat the same approach unchanged; we should reassess the underlying priority and adapt the next move."
            status = "attention"
        else:
            judgement = "The evidence is not strong enough for a clean success or failure call. I would keep the judgement provisional and gather the next piece of evidence before scaling or abandoning the approach."
            status = "attention"

        success_signal = str(outcome.get("success_signal") or "").strip()
        measured = f" Measured against the agreed success signal: {success_signal}." if success_signal else ""
        return CommandResponse(
            command="executive_outcome_review",
            status=status,
            message=f"Outcome review for {label}: {state}.{measured} {judgement}",
            data={
                "intent": "review_executive_action_outcome",
                "accepted": True,
                "outcome": dict(outcome),
                "business_outcome_status": state,
                "external_action_taken": False,
            },
        )

    def _outcome_status(self) -> CommandResponse:
        if self._awaiting_outcome:
            priority = self._awaiting_outcome.get("priority") if isinstance(self._awaiting_outcome.get("priority"), dict) else {}
            label = str(priority.get("label") or "the last completed action")
            success_signal = str(self._awaiting_outcome.get("success_signal") or "").strip()
            measurement = f" The agreed success signal is: {success_signal}." if success_signal else ""
            return CommandResponse(
                command="executive_outcome_status",
                status="attention",
                message=(
                    f"The delegated step for {label} is verified complete, but I do not yet have evidence that it achieved the business outcome."
                    f"{measurement} I would not call it successful until we can point to an actual result."
                ),
                data={
                    "intent": "check_executive_action_outcome",
                    "business_outcome_status": "unverified",
                    "awaiting_outcome": dict(self._awaiting_outcome),
                },
            )

        if self._last_outcome:
            outcome = dict(self._last_outcome)
            priority = outcome.get("priority") if isinstance(outcome.get("priority"), dict) else {}
            label = str(priority.get("label") or "the last completed action")
            state = str(outcome.get("outcome_status") or "inconclusive")
            summary = str(outcome.get("summary") or "").strip()
            suffix = f" {summary}" if summary else ""
            return CommandResponse(
                command="executive_outcome_status",
                status="healthy" if state == "positive" else "attention",
                message=f"The recorded business outcome for {label} is {state}.{suffix}",
                data={
                    "intent": "check_executive_action_outcome",
                    "business_outcome_status": state,
                    "outcome": outcome,
                },
            )

        return CommandResponse(
            command="executive_outcome_status",
            status="attention",
            message="I do not have a verified completed action with business-outcome evidence to assess yet.",
            data={"intent": "check_executive_action_outcome", "business_outcome_status": "unknown"},
        )

    def _augment_brief_with_outcome_watch(self, response: CommandResponse) -> CommandResponse:
        if not self._awaiting_outcome or not self._outcome_check_due():
            return response
        data = dict(response.data) if isinstance(response.data, dict) else {}
        priority = self._awaiting_outcome.get("priority") if isinstance(self._awaiting_outcome.get("priority"), dict) else {}
        label = str(priority.get("label") or "the last completed action")
        success_signal = str(self._awaiting_outcome.get("success_signal") or "").strip()
        data["executive_outcome_watch"] = {
            "status": "outcome_unverified",
            "action_id": self._awaiting_outcome.get("action_id"),
            "priority": dict(priority),
            "success_signal": success_signal,
        }
        measurement = f" Measure it against: {success_signal}." if success_signal else ""
        message = (
            f"Outcome check: the action for {label} was completed, but its business effect is still unverified."
            f"{measurement} Get outcome evidence before treating the work as successful or repeating it.\n"
            f"{response.message}"
        )
        return CommandResponse(response.command, "attention", message, data)

    def _outcome_check_due(self) -> bool:
        if not self._awaiting_outcome:
            return False
        value = str(self._awaiting_outcome.get("completed_at") or "").strip()
        if not value:
            return False
        try:
            completed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=timezone.utc)
        return self._now_utc() - completed.astimezone(timezone.utc) >= self.check_after

    @staticmethod
    def _extract_outcome(objects: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
        for item in objects:
            if not isinstance(item, dict):
                continue
            nested = item.get("executive_outcome")
            if isinstance(nested, dict):
                return dict(nested)
            if "outcome_status" in item and ("action_id" in item or "executive_action_id" in item):
                return dict(item)
        return None

    def _reject_outcome(self, reason: str) -> CommandResponse:
        return CommandResponse(
            command="executive_outcome_review",
            status="attention",
            message=f"I have not recorded a business outcome. {reason}",
            data={
                "intent": "review_executive_action_outcome",
                "accepted": False,
                "reason": reason,
                "business_outcome_status": "unverified" if self._awaiting_outcome else "unknown",
            },
        )

    def _now_utc(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _load_state(self) -> dict[str, Any]:
        empty = {"awaiting_outcome": None, "last_outcome": None}
        if not self.store_path.exists():
            return empty
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return empty
        if not isinstance(raw, dict):
            return empty
        awaiting = raw.get("awaiting_outcome")
        outcome = raw.get("last_outcome")
        return {
            "awaiting_outcome": dict(awaiting) if isinstance(awaiting, dict) else None,
            "last_outcome": dict(outcome) if isinstance(outcome, dict) else None,
        }

    def _persist_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "awaiting_outcome": dict(self._awaiting_outcome) if self._awaiting_outcome else None,
            "last_outcome": dict(self._last_outcome) if self._last_outcome else None,
        }
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)
