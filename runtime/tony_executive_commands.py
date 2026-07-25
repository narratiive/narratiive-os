from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable

from runtime.executive_brief import (
    BriefPeriod,
    ExecutiveBriefArchive,
    ExecutiveBriefService,
)
from runtime.friday_executive_review import (
    FridayExecutiveReviewService,
    ReviewRecord,
    ReviewRecordType,
)
from runtime.tony_command_service import CommandResponse, TonyCommandService


ReviewRecordLoader = Callable[[], Iterable[dict[str, Any]]]


class TonyExecutiveCommandService:
    """Add evidence-backed executive commands without duplicating Tony operations."""

    _PERIODS = {
        "morning": BriefPeriod.MORNING,
        "morning_brief": BriefPeriod.MORNING,
        "standup": BriefPeriod.MORNING,
        "evening": BriefPeriod.EVENING,
        "evening_review": BriefPeriod.EVENING,
        "end_of_day": BriefPeriod.EVENING,
    }
    _FRIDAY_COMMANDS = {"friday", "friday_review", "weekly_review", "executive_review"}

    def __init__(
        self,
        command_service: TonyCommandService,
        brief_service: ExecutiveBriefService | None = None,
        brief_archive: ExecutiveBriefArchive | None = None,
        friday_review_service: FridayExecutiveReviewService | None = None,
        friday_record_loader: ReviewRecordLoader | None = None,
        clock: Callable[[], datetime] | None = None,
        workspace_id: str = "narratiive",
    ) -> None:
        self.command_service = command_service
        self.brief_service = brief_service or ExecutiveBriefService()
        self.brief_archive = brief_archive
        self.friday_review_service = friday_review_service or FridayExecutiveReviewService()
        self.friday_record_loader = friday_record_loader
        self.clock = clock or datetime.now
        self.workspace_id = workspace_id

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
        if name in self._FRIDAY_COMMANDS:
            return self._execute_friday_review(objects)

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

    def _execute_friday_review(
        self,
        objects: Iterable[dict[str, Any]],
    ) -> CommandResponse:
        injected_records = tuple(objects)
        if injected_records:
            raw_records: Iterable[dict[str, Any]] = injected_records
        elif self.friday_record_loader is not None:
            try:
                raw_records = self.friday_record_loader()
            except Exception as exc:
                return self._error(
                    "friday_review",
                    "friday_review_untrusted",
                    f"Tony could not load trusted Friday evidence: {exc}",
                )
        else:
            return self._error(
                "friday_review",
                "friday_review_unavailable",
                "Friday Review evidence is not configured.",
            )

        try:
            records = tuple(self._review_record(item) for item in raw_records)
            review = self.friday_review_service.build(
                records,
                workspace_id=self.workspace_id,
                period_end=self.clock(),
            )
        except Exception as exc:
            return self._error(
                "friday_review",
                "friday_review_untrusted",
                f"Tony could not build a trusted Friday review: {exc}",
            )

        return CommandResponse(
            command="friday_review",
            status="healthy",
            message=review.render_compact(),
            data=review.to_dict(),
        )

    @staticmethod
    def _review_record(item: dict[str, Any]) -> ReviewRecord:
        evidence = item.get("evidence", ())
        if isinstance(evidence, str):
            evidence = (evidence,)
        return ReviewRecord(
            record_id=str(item["record_id"]),
            occurred_at=str(item["occurred_at"]),
            record_type=ReviewRecordType(str(item["record_type"])),
            summary=str(item["summary"]),
            evidence=tuple(str(value) for value in evidence),
            workspace_id=str(item["workspace_id"]),
            theme=str(item["theme"]) if item.get("theme") else None,
        )

    @staticmethod
    def _error(command: str, code: str, message: str) -> CommandResponse:
        return CommandResponse(
            command=command,
            status="error",
            message=message,
            data={"error_code": code},
        )
