from __future__ import annotations

from typing import Any, Iterable

from runtime.mission_control import MissionControlSnapshot
from runtime.mission_control_service import MissionControlService
from runtime.tony_command_service import CommandResponse, TonyCommandService


class TonyExecutiveService:
    """Single read-only command surface for Tony's executive and operational views.

    Mission Control is intentionally supplied as an evidence-backed snapshot by the
    caller. The service never invents connection, approval, workstream or progress
    state. Existing operational commands continue to use TonyCommandService.
    """

    MISSION_CONTROL_COMMANDS = {"mission_control", "mission", "overview"}

    def __init__(
        self,
        command_service: TonyCommandService,
        mission_control_service: MissionControlService | None = None,
    ) -> None:
        self.command_service = command_service
        self.mission_control_service = mission_control_service or MissionControlService()

    def execute(
        self,
        command: str,
        objects: Iterable[dict[str, Any]],
        *,
        mission_control_snapshot: MissionControlSnapshot | None = None,
    ) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""

        if name not in self.MISSION_CONTROL_COMMANDS:
            return self.command_service.execute(command, objects)

        if mission_control_snapshot is None:
            return CommandResponse(
                command="mission_control",
                status="error",
                message="Mission Control snapshot is unavailable.",
                data={"error_code": "mission_control_unavailable"},
            )

        response = self.mission_control_service.respond(mission_control_snapshot)
        return CommandResponse(
            command="mission_control",
            status=response.status,
            message=response.message,
            data=response.data,
        )

    def telegram_reply(
        self,
        command: str,
        objects: Iterable[dict[str, Any]],
        *,
        mission_control_snapshot: MissionControlSnapshot | None = None,
    ) -> str:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""

        if name in self.MISSION_CONTROL_COMMANDS and mission_control_snapshot is not None:
            return self.mission_control_service.telegram_reply(mission_control_snapshot)

        return self.execute(
            command,
            objects,
            mission_control_snapshot=mission_control_snapshot,
        ).message
