from __future__ import annotations

import re
from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyOutcomeEvidenceCommandService:
    """Interpret adaptive-test evidence before outcome accountability records a result.

    Caller-supplied labels and success thresholds are not trusted for adaptive tests
    with an agreed success signal. Tony derives the judgement from structured evidence
    against the criterion agreed before execution. When evidence is incomplete or a
    time-bound criterion is still live, he keeps the outcome inconclusive rather than
    inventing confidence.
    """

    _OUTCOME_COMMANDS = {"outcome_result", "record_outcome", "outcome_evidence"}
    _OPERATORS = {">", ">=", "<", "<=", "==", "!="}
    _EVENT_WINDOW_TYPES = {
        "qualified_event_within_business_days",
        "event_within_business_days",
    }
    _NUMBER_WORDS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
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
        success_signal = str(awaiting.get("success_signal") or "").strip()
        if not success_signal:
            return self.command_service.execute(command, materialized)

        transformed, interpretation = self._interpret(materialized, success_signal)
        response = self.command_service.execute(command, transformed)
        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["outcome_interpretation"] = interpretation
        message = response.message
        if interpretation["derived"]:
            message = (
                f"{message} Tony derived the outcome from the supplied evidence against the agreed success criterion rather than trusting a caller-supplied label or threshold."
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
        success_signal: str,
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
            derived = self._derive_measurement(measurement, success_signal)
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
                    "supplied_operator": derived.get("supplied_operator"),
                    "supplied_target_value": derived.get("supplied_target_value"),
                    "supplied_max_business_days": derived.get("supplied_max_business_days"),
                    "criterion_bound_to_success_signal": bool(
                        derived.get("criterion_bound_to_success_signal", False)
                    ),
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
            "supplied_operator": None,
            "supplied_target_value": None,
            "supplied_max_business_days": None,
            "criterion_bound_to_success_signal": False,
        }

    @classmethod
    def _derive_measurement(cls, measurement: Any, success_signal: str):
        if not isinstance(measurement, dict):
            return None
        measurement_type = str(measurement.get("type") or "").strip().casefold()
        if measurement_type in cls._EVENT_WINDOW_TYPES:
            agreed_days = cls._criterion_window_days(success_signal)
            return cls._derive_event_window(measurement, agreed_max_business_days=agreed_days)
        agreed_numeric = cls._criterion_numeric(success_signal)
        return cls._derive_numeric_measurement(measurement, agreed_numeric=agreed_numeric)

    @classmethod
    def _derive_numeric_measurement(
        cls,
        measurement: dict[str, Any],
        *,
        agreed_numeric: tuple[str, float] | None = None,
    ):
        supplied_operator = str(measurement.get("operator") or "").strip()
        supplied_target = measurement.get("target_value")
        if agreed_numeric is None:
            operator = supplied_operator
            target = supplied_target
            bound = False
        else:
            operator, target = agreed_numeric
            bound = True
        if operator not in cls._OPERATORS:
            return None
        observed = measurement.get("observed_value")
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
            "supplied_operator": supplied_operator or None,
            "supplied_target_value": supplied_target,
            "criterion_bound_to_success_signal": bound,
        }

    @classmethod
    def _derive_event_window(
        cls,
        measurement: dict[str, Any],
        *,
        agreed_max_business_days: int | None = None,
    ):
        event_observed = measurement.get("event_observed")
        event_qualified = measurement.get("event_qualified")
        elapsed = measurement.get("business_days_elapsed")
        supplied_maximum = measurement.get("max_business_days")
        maximum = agreed_max_business_days if agreed_max_business_days is not None else supplied_maximum
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
            "supplied_max_business_days": supplied_maximum,
            "criterion_bound_to_success_signal": agreed_max_business_days is not None,
        }

    @classmethod
    def _criterion_numeric(cls, success_signal: str) -> tuple[str, float] | None:
        match = re.search(
            r"(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*(%)?",
            success_signal,
        )
        if not match:
            return None
        operator = match.group(1)
        value = float(match.group(2))
        if match.group(3):
            value /= 100.0
        return operator, value

    @classmethod
    def _criterion_window_days(cls, success_signal: str) -> int | None:
        text = success_signal.casefold()
        match = re.search(r"within\s+(\d+)\s+business\s+days?", text)
        if match:
            return int(match.group(1))
        word_pattern = "|".join(cls._NUMBER_WORDS)
        match = re.search(rf"within\s+({word_pattern})\s+business\s+days?", text)
        if not match:
            return None
        return cls._NUMBER_WORDS[match.group(1)]

    @staticmethod
    def _looks_like_outcome(value: dict[str, Any]) -> bool:
        return bool(
            ("action_id" in value or "executive_action_id" in value)
            and ("evidence" in value or "outcome_status" in value or "outcome" in value)
        )
