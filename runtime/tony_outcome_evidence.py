from __future__ import annotations

from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyOutcomeEvidenceCommandService:
    """Interpret adaptive-test evidence before outcome accountability records a result.

    Caller-supplied labels are not trusted for adaptive tests with an agreed success
    signal. Tony derives the judgement from structured evidence when possible. When
    evidence is incomplete or a time-bound criterion is still live, he keeps the
    outcome inconclusive rather than inventing confidence.
    """

    _OUTCOME_COMMANDS = {"outcome_result", "record_outcome", "outcome_evidence"}
    _OPERATORS = {">", ">=", "<", "<=", "==", "!="}
    _EVENT_WINDOW_TYPES = {
        "qualified_event_within_business_days",
        "event_within_business_days",
    }

    def __init__(self, command_service) -> None:
        self.command_service = command_service

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        name = normalized.casefold().split(" ", 1)[0].lstrip("/") if normalized else ""
        materialized = tuple(objects)
        if name not in self._OUTCOME_COMMANDS:
            return self.command_service.execute(command, materialized)

        awaiting = getattr(self.command_service, "_awaiting_outcome", None)
        if not isinstance(awaiting, dict) or not bool(awaiting.get("adaptive_test")):
            return self.command_service.execute(command, materialized)
        if not str(awaiting.get("success_signal") or "").strip():
            return self.command_service.execute(command, materialized)

        transformed, interpretation = self._interpret(materialized)
        response = self.command_service.execute(command, transformed)
        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["outcome_interpretation"] = interpretation
        message = response.message
        if interpretation["derived"]:
            message = (
                f"{message} Tony derived the outcome from the supplied evidence rather than trusting a caller-supplied label."
            )
        elif interpretation["reason"] in {"measurement_missing", "criterion_still_open"}:
            if interpretation["reason"] == "criterion_still_open":
                message = (
                    f"{message} The agreed time-bound success criterion is still open, so I kept the judgement inconclusive rather than calling the test too early."
                )
            else:
                message = (
                    f"{message} The evidence did not include a measurable comparison against the agreed success signal, so I kept the judgement inconclusive."
                )
        return CommandResponse(response.command, response.status, message, data)

    def _interpret(
        self,
        objects: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
        output: list[dict[str, Any]] = []
        interpretation = self._empty_interpretation()
        transformed_once = False

        for item in objects:
            if not isinstance(item, dict):
                output.append(item)
                continue
            candidate = dict(item)
            nested = candidate.get("executive_outcome")
            target = dict(nested) if isinstance(nested, dict) else candidate
            if transformed_once or not self._looks_like_outcome(target):
                output.append(candidate)
                continue

            evidence = target.get("evidence")
            measurement = evidence.get("measurement") if isinstance(evidence, dict) else None
            derived = self._derive_measurement(measurement)
            if derived is None:
                target["outcome_status"] = "inconclusive"
            else:
                status = str(derived["status"])
                target["outcome_status"] = status
                interpretation = {
                    "derived": bool(derived["derived"]),
                    "reason": str(derived["reason"]),
                    "measurement_type": str(derived.get("measurement_type") or "numeric"),
                    "operator": str(derived.get("operator") or ""),
                    "observed_value": derived.get("observed_value"),
                    "target_value": derived.get("target_value"),
                    "criterion_met": derived.get("criterion_met"),
                    "event_observed": derived.get("event_observed"),
                    "event_qualified": derived.get("event_qualified"),
                    "business_days_elapsed": derived.get("business_days_elapsed"),
                    "max_business_days": derived.get("max_business_days"),
                }

            if isinstance(nested, dict):
                candidate["executive_outcome"] = target
            else:
                candidate = target
            output.append(candidate)
            transformed_once = True

        return tuple(output), interpretation

    @staticmethod
    def _empty_interpretation() -> dict[str, Any]:
        return {
            "derived": False,
            "reason": "measurement_missing",
            "measurement_type": "",
            "operator": "",
            "observed_value": None,
            "target_value": None,
            "criterion_met": None,
            "event_observed": None,
            "event_qualified": None,
            "business_days_elapsed": None,
            "max_business_days": None,
        }

    @classmethod
    def _derive_measurement(cls, measurement: Any):
        if not isinstance(measurement, dict):
            return None
        measurement_type = str(measurement.get("type") or "").strip().casefold()
        if measurement_type in cls._EVENT_WINDOW_TYPES:
            return cls._derive_event_window(measurement)
        return cls._derive_numeric_measurement(measurement)

    @classmethod
    def _derive_numeric_measurement(cls, measurement: dict[str, Any]):
        operator = str(measurement.get("operator") or "").strip()
        if operator not in cls._OPERATORS:
            return None
        observed = measurement.get("observed_value")
        target = measurement.get("target_value")
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            return None
        if not isinstance(target, (int, float)) or isinstance(target, bool):
            return None
        comparisons = {
            ">": observed > target,
            ">=": observed >= target,
            "<": observed < target,
            "<=": observed <= target,
            "==": observed == target,
            "!=": observed != target,
        }
        criterion_met = comparisons[operator]
        return {
            "status": "positive" if criterion_met else "negative",
            "derived": True,
            "reason": "measurement_compared",
            "measurement_type": "numeric",
            "operator": operator,
            "observed_value": observed,
            "target_value": target,
            "criterion_met": criterion_met,
        }

    @classmethod
    def _derive_event_window(cls, measurement: dict[str, Any]):
        event_observed = measurement.get("event_observed")
        event_qualified = measurement.get("event_qualified")
        elapsed = measurement.get("business_days_elapsed")
        maximum = measurement.get("max_business_days")
        if not isinstance(event_observed, bool) or not isinstance(event_qualified, bool):
            return None
        if not isinstance(elapsed, int) or isinstance(elapsed, bool) or elapsed < 0:
            return None
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
            return None

        within_window = elapsed <= maximum
        if event_observed and event_qualified and within_window:
            status = "positive"
            reason = "qualified_event_within_window"
            criterion_met: bool | None = True
            derived = True
        elif elapsed < maximum:
            status = "inconclusive"
            reason = "criterion_still_open"
            criterion_met = None
            derived = False
        else:
            status = "negative"
            reason = "qualified_event_not_achieved_in_window"
            criterion_met = False
            derived = True

        return {
            "status": status,
            "derived": derived,
            "reason": reason,
            "measurement_type": "qualified_event_within_business_days",
            "criterion_met": criterion_met,
            "event_observed": event_observed,
            "event_qualified": event_qualified,
            "business_days_elapsed": elapsed,
            "max_business_days": maximum,
        }

    @staticmethod
    def _looks_like_outcome(value: dict[str, Any]) -> bool:
        return bool(
            ("action_id" in value or "executive_action_id" in value)
            and ("evidence" in value or "outcome_status" in value or "outcome" in value)
        )
