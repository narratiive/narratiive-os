from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.agency_executive_brief import (
    AgencyBriefPeriod,
    AgencyExecutiveBriefService,
)
from runtime.agency_state_projection import AgencyStateProjector
from runtime.executive_brief import ExecutiveBriefArchive, ExecutiveBriefService
from runtime.executive_integration import IntegratedExecutiveBriefService
from runtime.friday_executive_review import (
    FridayExecutiveReviewService,
    ReviewRecord,
    ReviewRecordType,
)
from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_command_service import CommandResponse, TonyCommandService


ReviewRecordLoader = Callable[[], Iterable[dict[str, Any]]]
TerminologyPolicyLoader = Callable[[], TerminologyPolicy]
InboundLeadLoader = Callable[[], Iterable[InboundLead]]
_FRIDAY_RECORD_FIELDS = {
    "record_id",
    "occurred_at",
    "record_type",
    "summary",
    "evidence",
    "workspace_id",
}


class TonyExecutiveCommandService:
    """Add evidence-backed executive commands without exposing platform noise."""

    _PERIODS = {
        "morning": AgencyBriefPeriod.MORNING,
        "morning_brief": AgencyBriefPeriod.MORNING,
        "standup": AgencyBriefPeriod.MORNING,
        "evening": AgencyBriefPeriod.EVENING,
        "evening_review": AgencyBriefPeriod.EVENING,
        "end_of_day": AgencyBriefPeriod.EVENING,
    }
    _FRIDAY_COMMANDS = {"friday", "friday_review", "weekly_review", "executive_review"}
    _LEAD_COMMANDS = {"lead", "leads", "inbound", "inbound_leads", "pipeline"}

    def __init__(
        self,
        command_service: TonyCommandService,
        brief_service: ExecutiveBriefService | None = None,
        brief_archive: ExecutiveBriefArchive | None = None,
        friday_review_service: FridayExecutiveReviewService | None = None,
        friday_record_loader: ReviewRecordLoader | None = None,
        terminology_policy_loader: TerminologyPolicyLoader | None = None,
        clock: Callable[[], datetime] | None = None,
        workspace_id: str = "narratiive",
        agency_projector: AgencyStateProjector | None = None,
        agency_brief_service: AgencyExecutiveBriefService | None = None,
        inbound_lead_loader: InboundLeadLoader | None = None,
    ) -> None:
        self.command_service = command_service
        self.brief_service = brief_service or IntegratedExecutiveBriefService()
        self.brief_archive = brief_archive
        self.agency_projector = agency_projector or AgencyStateProjector()
        self.agency_brief_service = agency_brief_service or AgencyExecutiveBriefService()
        self.friday_review_service = friday_review_service or FridayExecutiveReviewService()
        self.friday_record_loader = friday_record_loader
        self.terminology_policy_loader = terminology_policy_loader or TerminologyPolicy.from_path
        self.clock = clock or datetime.now
        self.workspace_id = workspace_id

        self._lead_store_path: Path | None = None
        if inbound_lead_loader is None:
            self._lead_store_path = Path(
                os.getenv(
                    "TONY_INBOUND_LEADS_PATH",
                    ".runtime/inbound-leads.json",
                )
            ).resolve()
            self.inbound_lead_loader = FileInboundLeadStore(self._lead_store_path).read
            self._explicit_inbound_loader = False
        else:
            self.inbound_lead_loader = inbound_lead_loader
            self._explicit_inbound_loader = True

    @property
    def mission_control_loader(self):
        """Expose delegated configuration for bridge health and diagnostics."""
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def _lead_source_available(self) -> bool:
        if self._explicit_inbound_loader:
            return True
        return bool(self._lead_store_path and self._lead_store_path.exists())

    def execute(
        self,
        command: str,
        objects: Iterable[dict[str, Any]],
    ) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold().lstrip("/")
        name = lowered.split(" ", 1)[0] if lowered else ""
        if name in self._FRIDAY_COMMANDS:
            return self._execute_friday_review(objects)

        if self._is_lead_query(lowered):
            return self._execute_lead_query(lowered)

        period = self._PERIODS.get(name)
        if period is None:
            return self.command_service.execute(command, objects)

        loader = self.command_service.mission_control_loader
        if loader is None:
            return self._error(name, "mission_control_unavailable", "Mission Control is not configured.")

        try:
            policy = self.terminology_policy_loader()
            snapshot = loader()
            lead_source_available = self._lead_source_available()
            leads = tuple(self.inbound_lead_loader()) if lead_source_available else ()
            state = self.agency_projector.project(
                snapshot,
                leads,
                lead_source_available=lead_source_available,
            )
            brief = self.agency_brief_service.build(state, period)
            source_message = brief.render_compact()
            source_violations = policy.scan(source_message)
            message = policy.rewrite(source_message)
            violations = policy.scan(message)
            if violations:
                terms = ", ".join(sorted({item.term for item in violations}))
                raise ValueError(
                    f"executive brief uses retired terminology after rewrite under policy {policy.version}: {terms}"
                )

            if self.brief_archive is not None and not source_violations:
                legacy_period = self._legacy_period(period)
                archive_brief = self.brief_service.build(snapshot, legacy_period)
                self.brief_archive.store(archive_brief)
        except Exception as exc:
            return self._error(
                name,
                "executive_brief_untrusted",
                f"Tony could not build a trusted daily brief: {exc}",
            )

        canonical_command = "morning" if period is AgencyBriefPeriod.MORNING else "evening"
        data = brief.to_dict()
        data["agency_state"] = state.to_dict()
        data["terminology_policy_version"] = policy.version
        data["terminology_rewritten"] = bool(source_violations)
        data["inbound_leads_loaded"] = len(leads)
        data["inbound_lead_source_available"] = lead_source_available
        return CommandResponse(
            command=canonical_command,
            status=brief.status,
            message=message,
            data=data,
        )

    @classmethod
    def _is_lead_query(cls, lowered: str) -> bool:
        if not lowered:
            return False
        first = lowered.split(" ", 1)[0]
        if first in cls._LEAD_COMMANDS:
            return True
        phrases = (
            "inbound lead",
            "inbound leads",
            "today's leads",
            "todays leads",
            "yesterday's leads",
            "yesterdays leads",
            "commercial opportunities",
            "current opportunities",
        )
        return any(phrase in lowered for phrase in phrases)

    def _execute_lead_query(self, lowered: str) -> CommandResponse:
        if not self._lead_source_available():
            return self._error(
                "leads",
                "inbound_lead_source_unavailable",
                "I can't verify inbound leads because the live lead feed is unavailable.",
            )
        try:
            leads = tuple(self.inbound_lead_loader())
        except Exception as exc:
            return self._error(
                "leads",
                "inbound_lead_source_untrusted",
                f"I couldn't read the live inbound lead feed: {exc}",
            )

        scope = "current"
        scoped = leads
        now = self.clock()
        if "yesterday" in lowered:
            scope = "yesterday"
            target = (now - timedelta(days=1)).date()
            scoped = tuple(item for item in leads if self._lead_date(item) == target)
        elif "today" in lowered:
            scope = "today"
            target = now.date()
            scoped = tuple(item for item in leads if self._lead_date(item) == target)

        if not scoped:
            message = f"No inbound leads are recorded for {scope}."
        else:
            lines = [f"Inbound leads — {scope}: {len(scoped)}"]
            for lead in scoped[:10]:
                company = f" — {lead.company}" if lead.company else ""
                qualifiers = ", ".join(
                    value for value in (lead.source, lead.lead_temperature, lead.pipeline_stage) if value
                )
                lines.append(f"• {lead.contact}{company} ({qualifiers})")
                if lead.ai_summary:
                    lines.append(f"  {lead.ai_summary}")
                lines.append(f"  Next: {lead.recommended_next_action}")
            message = "\n".join(lines)

        return CommandResponse(
            command="leads",
            status="healthy",
            message=message,
            data={
                "scope": scope,
                "count": len(scoped),
                "leads": [item.to_dict() for item in scoped],
                "inbound_lead_source_available": True,
            },
        )

    @staticmethod
    def _lead_date(lead: InboundLead):
        value = lead.created_at.strip()
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.date()

    @staticmethod
    def _legacy_period(period: AgencyBriefPeriod):
        from runtime.executive_brief import BriefPeriod

        return BriefPeriod.MORNING if period is AgencyBriefPeriod.MORNING else BriefPeriod.EVENING

    def _execute_friday_review(
        self,
        objects: Iterable[dict[str, Any]],
    ) -> CommandResponse:
        injected_records = tuple(objects)
        if self.friday_record_loader is not None:
            try:
                raw_records: Iterable[dict[str, Any]] = self.friday_record_loader()
            except Exception as exc:
                return self._error(
                    "friday_review",
                    "friday_review_untrusted",
                    f"Tony could not load trusted Friday evidence: {exc}",
                )
        elif injected_records and self._looks_like_review_evidence(injected_records):
            raw_records = injected_records
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
    def _looks_like_review_evidence(items: tuple[dict[str, Any], ...]) -> bool:
        return any(
            isinstance(item, dict) and bool(_FRIDAY_RECORD_FIELDS.intersection(item))
            for item in items
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
