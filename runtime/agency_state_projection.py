from __future__ import annotations

from typing import Any, Iterable, Mapping

from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.inbound_leads import InboundLead
from runtime.executive_visibility import ExecutiveVisibilityPolicy
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
        summaries = {
            str(item.get("run_id") or ""): item
            for item in getattr(snapshot, "workflow_runs", ())
            if isinstance(item, Mapping) and str(item.get("run_id") or "")
        }
        authoritative = self._authoritative_run_ids(summaries.values())
        items = []
        for workstream in snapshot.workstreams:
            run_id = self._workflow_run_id(workstream.workstream_id)
            if run_id and run_id in summaries and run_id not in authoritative:
                continue
            items.append(self._project_workstream(workstream, summaries.get(run_id)))

        for lead in ExecutiveVisibilityPolicy().visible_leads(leads):
            items.append(lead.to_agency_item())

        for index, approval in enumerate(snapshot.approvals_required):
            run_id = self._approval_run_id(approval)
            summary = summaries.get(run_id)
            if run_id and summary is not None and run_id not in authoritative:
                continue
            title = self._humanise(approval)
            next_action = f"Decide whether to approve {title}."
            entity_id = approval
            aliases: tuple[str, ...] = ()
            if summary is not None:
                company = str(summary.get("company") or summary.get("entity_id") or "this work")
                workflow = str(summary.get("workflow_id") or "workflow")
                title = f"Decision required: {company} — {workflow}"
                next_action = str(summary.get("proposed_next_action") or f"Review the current {workflow} artefact and approve, reject or request revision.")
                entity_id = str(summary.get("entity_id") or summary.get("client_id") or run_id)
                aliases = tuple(filter(None, (company, run_id)))
            items.append(
                AgencyItem(
                    item_id=f"approval-{index}",
                    area=self._classify(approval),
                    title=title,
                    status="decision_required",
                    next_action=next_action,
                    owner="Matt",
                    evidence=(approval,),
                    requires_matt=True,
                    blocks_agency_outcome=self._has_business_consequence(approval),
                    entity_id=entity_id,
                    aliases=aliases,
                    classification="genuine_approval_request",
                    significance="P1",
                    why_matters="The current authoritative artefact cannot progress through its human gate without a founder decision.",
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
                        entity_id="commercial-pipeline",
                        classification="commercial_empty_state",
                        significance="P3",
                        why_matters="An empty verified pipeline creates a near-term commercial risk.",
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
                        entity_id="inbound-lead-feed",
                        classification="operational_exception",
                        significance="P3",
                        why_matters="Commercial decisions are unsafe while the authoritative lead feed is unavailable.",
                    )
                )

        return AgencyState.from_items(snapshot.generated_at, self._deduplicate(items))

    def _project_workstream(
        self, item: WorkstreamStatus, summary: Mapping[str, Any] | None = None
    ) -> AgencyItem:
        text = " ".join(
            part for part in (item.workstream_id, item.title, item.next_action, item.blocker or "") if part
        )
        area = self._classify(text)
        is_platform = area in {AgencyArea.ENGINEERING, AgencyArea.INFRASTRUCTURE}
        business_consequence = self._has_business_consequence(text)
        requires_matt = item.owner.strip().casefold() == "matt"

        entity_id = str((summary or {}).get("entity_id") or (summary or {}).get("client_id") or item.workstream_id)
        company = str((summary or {}).get("company") or "")
        significance = "P1" if requires_matt else "P3"
        if item.state == "blocked" and is_platform and business_consequence:
            significance = "P0"
        return AgencyItem(
            item_id=item.workstream_id,
            area=area,
            title=item.title,
            status=item.state,
            next_action=item.next_action,
            owner=item.owner,
            evidence=item.evidence,
            blocked=item.state == "blocked",
            blocks_agency_outcome=(item.state == "blocked" and is_platform and business_consequence),
            requires_matt=requires_matt,
            entity_id=entity_id,
            aliases=tuple(filter(None, (company, item.workstream_id))),
            classification="operational_exception" if item.state == "blocked" else "current_authoritative_workflow",
            significance=significance,
            why_matters=(
                "A current operational exception is preventing progress on this work."
                if item.state == "blocked"
                else "This is material progress on the current authoritative workflow."
            ),
        )

    @staticmethod
    def _workflow_run_id(workstream_id: str) -> str:
        return workstream_id.split(":", 1)[1] if workstream_id.startswith("workflow:") else ""

    @staticmethod
    def _approval_run_id(approval: str) -> str:
        if not approval.startswith("workflow:"):
            return ""
        return approval.split(":", 2)[1]

    @staticmethod
    def _authoritative_run_ids(summaries: Iterable[Mapping[str, Any]]) -> set[str]:
        latest: dict[tuple[str, str], Mapping[str, Any]] = {}
        for summary in summaries:
            entity = str(summary.get("entity_id") or summary.get("client_id") or summary.get("company") or "").casefold()
            workflow = str(summary.get("workflow_id") or "").casefold()
            key = (entity, workflow)
            current = latest.get(key)
            if current is None or (str(summary.get("updated_at") or ""), str(summary.get("run_id") or "")) > (
                str(current.get("updated_at") or ""), str(current.get("run_id") or "")
            ):
                latest[key] = summary
        return {str(item.get("run_id") or "") for item in latest.values()}

    @staticmethod
    def _deduplicate(items: Iterable[AgencyItem]) -> tuple[AgencyItem, ...]:
        priority = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
        selected: dict[tuple[str, AgencyArea], AgencyItem] = {}
        for item in items:
            key = ((item.entity_id or item.item_id).casefold(), item.area)
            current = selected.get(key)
            rank = (priority.get(item.significance, 4), 0 if item.requires_matt else 1, 0 if item.blocked else 1)
            current_rank = (
                priority.get(current.significance, 4), 0 if current.requires_matt else 1, 0 if current.blocked else 1
            ) if current else None
            if current is None or rank < current_rank:
                selected[key] = item
        return tuple(selected.values())

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
