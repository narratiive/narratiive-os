from __future__ import annotations

from typing import Any, Iterable

from runtime.executive_brief import (
    BriefPeriod,
    ExecutiveBriefArchive,
    ExecutiveBriefService,
)
from runtime.tony_command_service import CommandResponse, TonyCommandService


class TonyExecutiveCommandService:
    """Add evidence-backed daily brief commands without duplicating Tony operations."""

    _PERIODS = {
        "morning": BriefPeriod.MORNING,
        "morning_brief": BriefPeriod.MORNING,
        "standup": BriefPeriod.MORNING,
        "evening": BriefPeriod.EVENING,
        "evening_review": BriefPeriod.EVENING,
        "end_of_day": BriefPeriod.EVENING,
    }

    def __init__(
        self,
        command_service: TonyCommandService,
        brief_service: ExecutiveBriefService | None = None,
        brief_archive: ExecutiveBriefArchive | None = None,
    ) -> None:
        self.command_service = command_service
        self.brief_service = brief_service or ExecutiveBriefService()
        self.brief_archive = brief_archive

    @property
    def mission_control_loader(self):
        """Expose delegated configuration for bridge health and diagnostics."""
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(
        self,
        command: str,
        objects: Iterable[dict[str, Any]],
    ) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        period = self._PERIODS.get(name)
        if period is None:
            return self.command_service.execute(command, objects)

        loader = self.command_service.mission_control_loader
        if loader is None:
            return self._error(
                name,
                "mission_control_unavailable",
                "Mission Control is not configured.",
            )

        try:
            snapshot = loader()
            if self.github_configured and snapshot.github_work is None:
                raise ValueError(
                    "GitHub awareness is configured but live GitHub state is unavailable"
                )
            brief = self.brief_service.build(snapshot, period)
            if self.brief_archive is not None:
                self.brief_archive.store(brief)
        except Exception as exc:
            return self._error(
                name,
                "executive_brief_untrusted",
                f"Tony could not build a trusted daily brief: {exc}",
            )

        canonical_command = "morning" if period is BriefPeriod.MORNING else "evening"
        return CommandResponse(
            command=canonical_command,
            status=brief.status,
            message=brief.render_compact(),
            data=brief.to_dict(),
        )

    @staticmethod
    def _error(command: str, code: str, message: str) -> CommandResponse:
        return CommandResponse(
            command=command,
            status="error",
            message=message,
            data={"error_code": code},
        )
