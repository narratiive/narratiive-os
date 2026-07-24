from __future__ import annotations

from typing import Any, Iterable

from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_command_service import CommandResponse


class TonyTerminologyCommandService:
    """Fail closed when Tony output contains repository-retired language."""

    def __init__(self, command_service, policy: TerminologyPolicy | None = None) -> None:
        self.command_service = command_service
        self.policy = policy or TerminologyPolicy.from_path()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        response = self.command_service.execute(command, objects)
        violations = self.policy.scan_many(self._strings(response.message, response.data))
        if not violations:
            return response

        terms = sorted({violation.term for violation in violations}, key=str.casefold)
        return CommandResponse(
            command=response.command,
            status="error",
            message="Tony output was blocked because it used retired Narratiive terminology.",
            data={
                "error_code": "terminology_violation",
                "policy_version": self.policy.version,
                "retired_terms": terms,
            },
        )

    @classmethod
    def _strings(cls, message: str, data: Any) -> Iterable[str]:
        yield message
        yield from cls._walk(data)

    @classmethod
    def _walk(cls, value: Any) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, nested in value.items():
                if isinstance(key, str):
                    yield key
                yield from cls._walk(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                yield from cls._walk(nested)
