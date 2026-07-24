from __future__ import annotations

from typing import Any, Iterable

from runtime.tony_capabilities import TonyCapabilityRegistry
from runtime.tony_command_service import CommandResponse


class TonyCapabilityCommandService:
    """Expose Tony's canonical capability registry through deterministic commands."""

    _COMMANDS = {"capabilities", "commands", "help"}

    def __init__(self, command_service, registry: TonyCapabilityRegistry | None = None) -> None:
        self.command_service = command_service
        self.registry = registry or TonyCapabilityRegistry()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        if name not in self._COMMANDS:
            return self.command_service.execute(command, objects)

        configured = self._configured_features()
        snapshot = self.registry.snapshot(configured)
        return CommandResponse(
            command="capabilities",
            status=snapshot["status"],
            message=self.registry.telegram_summary(configured),
            data=snapshot,
        )

    def _configured_features(self) -> set[str]:
        features: set[str] = set()
        base = self.command_service
        while hasattr(base, "command_service"):
            base = base.command_service
        if getattr(base, "mission_control_loader", None) is not None:
            features.add("mission_control")
        if getattr(base, "execution_journal", None) is not None:
            features.add("execution_journal")
        if getattr(self.command_service, "diagnostics_runner", None) is not None:
            features.add("diagnostics")
        return features
