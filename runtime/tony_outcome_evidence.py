from __future__ import annotations

from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyOutcomeEvidenceCommandService:
    """Interpret adaptive-test evidence before outcome accountability records a result.

    Caller-supplied labels are not trusted for adaptive tests with an agreed success
    signal. When structured measurement exists Tony derives the judgement himself.
    When it does not, he keeps the result inconclusive rather than accepting an
    asserted positive/negative label as evidence.
    """

    _OUTCOME_COMMANDS = {"outcome_result", "record_outcome", "outcome_evidence"}
    _OPERATORS = {">", ">=", "<", "<=", "==", "!="}

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
                f"{message} Tony derived the outcome from the supplied measurement rather than trusting a caller-supplied label."
            )
        elif interpretation["reason"] == "measurement_missing":
            message = (
                f"{message} The evidence did not include a measurable comparison against the agreed success signal, so I kept the judgement inconclusive."
            )
        return CommandResponse(response.command, response.status, message, data)

    def _interpret(
        self,
        objects: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
        output: list[dict[str, Any]] = []
        interpretation = {
            "derived": False,
            "reason": "measurement_missing",
            "operator": "",
            "observed_value": None,
            "target_value": None,
            "criterion_met": None,
        }
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
                criterion_met, observed, target_value, operator = derived
                target["outcome_status"] = "positive" if criterion_met else "negative"
                interpretation = {
                    "derived": True,
                    "reason": "measurement_compared",
                    "operator": operator,
                    "observed_value": observed,
                    "target_value": target_value,
                    "criterion_met": criterion_met,
                }

            if isinstance(nested, dict):
                candidate["executive_outcome"] = target
            else:
                candidate = target
            output.append(candidate)
            transformed_once = True

        return tuple(output), interpretation

    @classmethod
    def _derive_measurement(cls, measurement: Any):
        if not isinstance(measurement, dict):
            return None
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
        return comparisons[operator], observed, target, operator

    @staticmethod
    def _looks_like_outcome(value: dict[str, Any]) -> bool:
        return bool(
            ("action_id" in value or "executive_action_id" in value)
            and ("evidence" in value or "outcome_status" in value or "outcome" in value)
        )
