from __future__ import annotations

from typing import Iterable

from runtime.autonomy_planner import AutonomyPlan, TonyAutonomyPlanner
from runtime.client_lifecycle import AcquisitionPath, ClientLifecycleRecord, ClientLifecycleStage
from runtime.inbound_leads import InboundLead


_PIPELINE_STAGE_MAP = {
    "lead": ClientLifecycleStage.LEAD,
    "new": ClientLifecycleStage.LEAD,
    "new diagnostic": ClientLifecycleStage.LEAD,
    "research": ClientLifecycleStage.RESEARCH,
    "blueprint lite": ClientLifecycleStage.BLUEPRINT_LITE,
    "outreach": ClientLifecycleStage.OUTREACH,
    "discovery": ClientLifecycleStage.MEETING,
    "meeting": ClientLifecycleStage.MEETING,
    "proposal": ClientLifecycleStage.PROPOSAL,
    "delivery": ClientLifecycleStage.DELIVERY,
    "invoice": ClientLifecycleStage.INVOICE,
    "complete": ClientLifecycleStage.COMPLETE,
    "completed": ClientLifecycleStage.COMPLETE,
}


def project_inbound_lead(lead: InboundLead) -> ClientLifecycleRecord:
    """Project Notion-backed inbound state without claiming unobserved progression."""
    pipeline_stage = " ".join(lead.pipeline_stage.strip().casefold().replace("_", " ").split())
    stage = _PIPELINE_STAGE_MAP.get(pipeline_stage, ClientLifecycleStage.LEAD)
    acquisition_path = (
        AcquisitionPath.LEGACY
        if stage in {ClientLifecycleStage.RESEARCH, ClientLifecycleStage.OUTREACH}
        else AcquisitionPath.INBOUND
    )
    client_name = lead.company.strip() or lead.contact.strip()
    evidence = tuple(
        value
        for value in (
            f"inbound_lead:{lead.lead_id}",
            f"source:{lead.source}" if lead.source else "",
            f"status:{lead.status}" if lead.status else "",
            f"pipeline_stage:{lead.pipeline_stage}" if lead.pipeline_stage else "",
            f"lead_temperature:{lead.lead_temperature}" if lead.lead_temperature else "",
            f"notion:{lead.notion_url}" if lead.notion_url else "",
        )
        if value
    )
    return ClientLifecycleRecord(
        client_id=lead.lead_id,
        client_name=client_name,
        stage=stage,
        owner="Tony",
        next_action=lead.recommended_next_action,
        evidence=evidence,
        blocked=False,
        blocker=None,
        requires_matt=False,
        acquisition_path=acquisition_path,
    )


def project_inbound_portfolio(leads: Iterable[InboundLead]) -> tuple[ClientLifecycleRecord, ...]:
    return tuple(project_inbound_lead(lead) for lead in leads)


def plan_inbound_autonomy(
    leads: Iterable[InboundLead],
    *,
    planner: TonyAutonomyPlanner | None = None,
) -> AutonomyPlan:
    """Return Tony's safe internal queue and human queue for live inbound work."""
    service = planner or TonyAutonomyPlanner()
    return service.plan(project_inbound_portfolio(leads))
