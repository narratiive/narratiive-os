from __future__ import annotations

from typing import Iterable

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.inbound_leads import InboundLead
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus


class AgencyStateProjector:
    """Translate operational and live commercial evidence into Tony's agency view."""

    _AREA_KEYWORDS: tuple[tuple[AgencyArea, tuple[str, ...]], ...] = (
        (AgencyArea.COMMERCIAL, ("lead", "pipeline", "prospect", "outreach", "proposal", "discovery", "opportunity", "sales")),
        (AgencyArea.CLIENTS, ("client", "account", "relationship", "retainer")),
        (AgencyArea.DELIVERY, ("deliver", "campaign", "project", "brief", "research", "blueprint", "creative", "newsletter", "signal")),
        (AgencyArea.FINANCE, ("revenue", "invoice", "cash", "finance", "payment", "margin", "budget")),
        (AgencyArea.AUTOMATION, ("automation", "workflow", "n8n", "make", "telegram", "notion", "email")),
        (AgencyArea.INFRASTRUCTURE, ("runtime", "bridge", "server", "webhook", "credential", "connection", "infrastructure")),
        (AgencyArea.ENGINEERING, ("mission control", "github", "pull request", "repository", "merge", "validation", "test", "code", "engineering")),
    )

    _BUSINESS_CONSEQUENCE_WORDS = (
        "client",
        "lead",
        "prospect",
        "revenue",
        "delivery",
        "campaign",
        "invoice",
        "outreach",
        "proposal",
        "enquiry",
    )

    def project(
        self,
        snapshot: MissionControlSnapshot,
        leads: Iterable[InboundLead] = (),
        *,
        lead_source_available: bool = False,
    ) -> AgencyState:
        items = [self._project_workstream(item) for item in snapshot.workstreams]

        for lead in leads:
            # Completed leads remain in Notion history but should not clutter the
            # daily commercial brief. Active/new/waiting leads stay visible.
            if lead.status.casefold() != "complete":
                items.append(lead.to_agency_item())

        for index, approval in enumerate(snapshot.approvals_required):
            items.append(
                AgencyItem(
                    item_id=f"approval-{index}",
                    area=self._classify(approval),
                    title=self._humanise(approval),
                    status="decision_required",
                    next_action="Review and decide this item.",
                    owner="Matt",
                    evidence=(approval,),
                    requires_matt=True,
                    blocks_agency_outcome=self._has_business_consequence(approval),
                )
            )

        if not any(item.area in {AgencyArea.COMMERCIAL, AgencyArea.CLIENTS} for item in items):
            if lead_source_available:
                items.append(
                    AgencyItem(
                        item_id="commercial-empty-state",
                        area=AgencyArea.COMMERCIAL,
                        title="No active lead or qualified opportunity currently recorded",
                        status="attention",
                        next_action="Create and progress the next commercial opportunity.",
                        evidence=("The live inbound lead feed is connected and contains no active leads.",),
                    )
                )
            else:
                # Missing commercial telemetry is a trust/watchout issue, not by
                # itself a reason to label the whole agency blocked. Crucially,
                # Tony also does not infer that the pipeline is empty.
                items.append(
                    AgencyItem(
                        item_id="commercial-source-unavailable",
                        area=AgencyArea.AUTOMATION,
                        title="Inbound lead feed unavailable",
                        status="attention",
                        next_action="Restore the live lead feed before making claims about pipeline emptiness.",
                        evidence=("Tony could not verify the canonical inbound lead source.",),
                    )
                )

        return AgencyState.from_items(snapshot.generated_at, items)

    def _project_workstream(self, item: WorkstreamStatus) -> AgencyItem:
        text = " ".join(
            part for part in (item.workstream_id, item.title, item.next_action, item.blocker or "") if part
        )
        area = self._classify(text)
        is_platform = area in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}
        business_consequence = self._has_business_consequence(text)
        requires_matt = item.owner.strip().casefold() == "matt"

        return AgencyItem(
            item_id=item.workstream_id,
            area=area,
            title=item.title,
            status=item.state,
            next_action=item.next_action,
            owner=item.owner,
            evidence=item.evidence,
            blocked=item.state == "blocked",
            blocks_agency_outcome=(business_consequence if is_platform else item.state == "blocked"),
            requires_matt=requires_matt,
        )

    @classmethod
    def _classify(cls, text: str) -> AgencyArea:
        normalised = text.casefold()
        scored = (
            (sum(normalised.count(keyword) for keyword in keywords), priority, area)
            for priority, (area, keywords) in enumerate(cls._AREA_KEYWORDS)
        )
        score, _, area = max(scored, key=lambda candidate: (candidate[0], -candidate[1]))
        return area if score else AgencyArea.OPERATIONS

    @classmethod
    def _has_business_consequence(cls, text: str) -> bool:
        normalised = text.casefold()
        return any(keyword in normalised for keyword in cls._BUSINESS_CONSEQUENCE_WORDS)

    @staticmethod
    def _humanise(value: str) -> str:
        return " ".join(value.replace(":", " ").replace("_", " ").split()).strip().capitalize()
