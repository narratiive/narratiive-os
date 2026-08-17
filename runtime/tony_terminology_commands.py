from __future__ import annotations

from typing import Any, Iterable

from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_command_service import CommandResponse
from runtime.tony_conversational_intent import TonyConversationalIntentCommandService


class TonyTerminologyCommandService:
    """Expose canonical vocabulary and rewrite retired language before delivery."""

    VOCABULARY_COMMANDS = {"vocabulary", "terminology", "canon"}

    def __init__(self, command_service, policy: TerminologyPolicy | None = None) -> None:
        self.command_service = (
            command_service
            if isinstance(command_service, TonyConversationalIntentCommandService)
            else TonyConversationalIntentCommandService(command_service)
        )
        self.policy = policy or TerminologyPolicy.from_path()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        if name in self.VOCABULARY_COMMANDS:
            return self._vocabulary()

        response = self.command_service.execute(command, objects)
        violations = self.policy.scan_many(self._strings(response.message, response.data))
        if not violations:
            return response

        rewritten_message = self.policy.rewrite(response.message)
        rewritten_data = self._rewrite_value(response.data)
        remaining = self.policy.scan_many(self._strings(rewritten_message, rewritten_data))
        if remaining:
            return CommandResponse(
                command=response.command,
                status="error",
                message=(
                    "I couldn't phrase that response safely using the current Narratiive language. "
                    "The underlying information is still available, but I need to reframe the wording."
                ),
                data={
                    "error_code": "terminology_rewrite_failed",
                    "policy_version": self.policy.version,
                },
            )

        return CommandResponse(
            command=response.command,
            status=response.status,
            message=rewritten_message,
            data=rewritten_data,
        )

    def _vocabulary(self) -> CommandResponse:
        approved = tuple(
            f"{entry['term']} — {entry['use']}"
            for entry in self.policy.approved_terms
        )
        unsettled = tuple(
            f"{entry['concept']} — {entry['rule']}"
            for entry in self.policy.unsettled_terms
        )
        retired = tuple(entry["term"] for entry in self.policy.retired_terms)

        lines = [
            f"Narratiive vocabulary v{self.policy.version}",
            f"Version note: {self.policy.version_note}",
        ]
        if approved:
            lines.append("Approved:")
            lines.extend(f"- {item}" for item in approved)
        if unsettled:
            lines.append("Unsettled:")
            lines.extend(f"- {item}" for item in unsettled)
        if retired:
            lines.append("Retired:")
            lines.extend(f"- {item}" for item in retired)

        return CommandResponse(
            command="vocabulary",
            status="ok",
            message="\n".join(lines),
            data={
                "policy_version": self.policy.version,
                "version_note": self.policy.version_note,
                "approved_terms": list(self.policy.approved_terms),
                "unsettled_terms": list(self.policy.unsettled_terms),
                "retired_terms": list(self.policy.retired_terms),
            },
        )

    def _rewrite_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.policy.rewrite(value)
        if isinstance(value, dict):
            return {key: self._rewrite_value(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [self._rewrite_value(nested) for nested in value]
        if isinstance(value, tuple):
            return tuple(self._rewrite_value(nested) for nested in value)
        if isinstance(value, set):
            return {self._rewrite_value(nested) for nested in value}
        return value

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
