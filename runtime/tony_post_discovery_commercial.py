from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_command_service import CommandResponse


class TonyPostDiscoveryCommercialCommandService:
    """Turn a verified discovery review into a bounded, approval-gated next move.

    When the evidence supports progressing, Tony prepares one evidence-grounded,
    copyable proposal commission brief for Matt to take to Claude himself. Tony
    never drafts, invents or silently approves the proposal, and never commits a
    generation worker on Matt's behalf. The brief requires the exact canonical
    Groundwork artefact for this lead; a Groundwork brief that was only produced
    manually, outside canonical workflow state, is never silently treated as
    approved evidence — Tony fails closed and offers the governed registration
    path below instead.
    """

    APPROVALS = {"do that", "do it", "go ahead", "yes do that", "yes, do that", "prepare it", "prepare the brief", "prepare the proposal"}

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path, groundwork_store=None) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.groundwork_store = groundwork_store
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending = self.state.get("pending") if isinstance(self.state.get("pending"), dict) else None
        if pending and normalized in self.APPROVALS:
            return self._prepare(pending)
        response = self.command_service.execute(command, objects)
        data = response.data if isinstance(response.data, dict) else {}
        return self._route(response) if data.get("execution_status") == "discovery_outcome_review_ready" else response

    def _route(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data)
        outcome = data.get("discovery_outcome") if isinstance(data.get("discovery_outcome"), dict) else {}
        review = outcome.get("review_evidence") if isinstance(outcome.get("review_evidence"), dict) else {}
        recommendation = str(outcome.get("recommended_next_action") or "").strip()
        combined = " ".join(str(review.get(k) or "") for k in ("disposition", "recommendation", "recommended_next_action", "next_action", "summary")).casefold()
        positive = any(t in combined for t in ("proposal", "advance", "proceed", "buying signal", "positive"))
        stop = any(t in combined for t in ("no fit", "not a fit", "decline", "stop", "close", "nurture"))
        if not positive or stop:
            data["execution_status"] = "post_discovery_no_proposal_recommended"
            data["post_discovery_commercial"] = {"state": "recommendation_only", "recommended_next_action": recommendation, "write_actions_allowed": False}
            return CommandResponse(response.command, response.status, response.message + " I am not progressing this into proposal preparation automatically. Any close, nurture or Notion stage change remains a separate approval-gated decision.", data)
        pending = {
            "calendar_event_id": str(outcome.get("calendar_event_id") or ""),
            "lead_id": str(outcome.get("lead_id") or ""),
            "contact": str(outcome.get("contact") or ""),
            "company": str(outcome.get("company") or ""),
            "meeting_evidence": dict(outcome.get("meeting_evidence") or {}) if isinstance(outcome.get("meeting_evidence"), dict) else {},
            "review_evidence": dict(review),
            "recommended_next_action": recommendation,
        }
        self.state["pending"] = pending
        self._persist()
        data["execution_status"] = "post_discovery_proposal_approval_required"
        data["post_discovery_commercial"] = {"state": "awaiting_preparation_approval", "approval_required": True, "write_actions_allowed": False, **pending}
        return CommandResponse(
            response.command,
            response.status,
            response.message + " The evidence supports preparing a proposal commission brief. I have not written or sent a proposal. Say 'do that' to approve preparing that brief for you to take to Claude.",
            data,
        )

    def _prepare(self, pending: dict[str, Any]) -> CommandResponse:
        lead_id = str(pending.get("lead_id") or "")
        groundwork = self._load_groundwork(lead_id)
        if isinstance(groundwork, CommandResponse):
            return groundwork
        brief = build_proposal_commission_brief(pending, groundwork)
        self.state["pending"] = None
        self.state["last_prepared"] = {**dict(pending), "commission_brief": brief, "groundwork_canonical_run_id": groundwork["canonical_run_id"], "groundwork_version": groundwork["version"]}
        self._persist()
        return CommandResponse(
            "post_discovery_commercial",
            "healthy",
            "Here is the evidence-grounded proposal commission brief, combining the verified discovery evidence with the canonical Groundwork artefact. Copy the commission below into Claude yourself; I have not generated a proposal and have not sent or changed anything.",
            {
                "execution_status": "proposal_brief_ready",
                "proposal_commission_brief": brief,
                "post_discovery_commercial": {"state": "proposal_brief_ready", **dict(pending)},
                "approval_required_for_external_proposal": True,
                "external_action_taken": False,
            },
        )

    def _load_groundwork(self, lead_id: str) -> dict[str, Any] | CommandResponse:
        if self.groundwork_store is None:
            return self._groundwork_recovery_response(lead_id, "No canonical Groundwork store is configured, so I cannot verify a Groundwork artefact for this lead.")
        try:
            record = self.groundwork_store.get(lead_id)
        except Exception as exc:
            return self._groundwork_recovery_response(lead_id, f"The canonical Groundwork store could not be read: {exc}")
        if not isinstance(record, dict):
            return self._groundwork_recovery_response(lead_id, "No canonical Groundwork artefact is recorded for this lead.")
        versions = record.get("versions")
        if not isinstance(versions, list) or not versions:
            return self._groundwork_recovery_response(lead_id, "A Groundwork preparation job exists for this lead, but no completed, quality-passed version is recorded yet.")
        version = versions[-1]
        if not isinstance(version, dict) or not isinstance(version.get("evidence"), dict):
            return self._groundwork_recovery_response(lead_id, "The recorded Groundwork version is missing its evidence contract, so I will not treat it as canonical.")
        return {
            "canonical_run_id": str(record.get("canonical_run_id") or lead_id),
            "version": int(version.get("version") or 0),
            "state": str(record.get("state") or ""),
            "diagnostic_input_package": dict(version.get("diagnostic_input_package") or {}),
            "evidence": dict(version.get("evidence")),
        }

    def _groundwork_recovery_response(self, lead_id: str, reason: str) -> CommandResponse:
        return CommandResponse(
            "post_discovery_commercial",
            "healthy",
            (
                f"{reason} The manually prepared brief some people hold for this lead is outside canonical workflow state and I will not silently treat it as approved evidence. "
                "If a Groundwork brief genuinely exists but was produced manually outside this system, use the governed manual Groundwork registration path "
                "(record its exact content, producer and your rationale as an explicit, unapproved exception) before I can prepare the proposal commission brief. "
                "I have not prepared or invented a brief."
            ),
            {
                "execution_status": "proposal_brief_requires_groundwork_registration",
                "post_discovery_commercial": {"state": "awaiting_groundwork_registration", "lead_id": lead_id, "approval_required": True, "write_actions_allowed": False},
                "external_action_taken": False,
            },
        )

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "last_prepared": None}
        return value if isinstance(value, dict) else {"pending": None, "last_prepared": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def build_proposal_commission_brief(pending: Mapping[str, Any], groundwork: Mapping[str, Any]) -> dict[str, Any]:
    """Combine verified Discovery evidence with the canonical Groundwork artefact.

    Produces the structured brief Matt reviews plus one copyable commission
    block for external Claude. This never invents a verdict Tony is not
    authorised to make: Groundwork hypotheses and Discovery findings are
    presented side by side, not pre-reconciled.
    """

    meeting_evidence = dict(pending.get("meeting_evidence") or {})
    review_evidence = dict(pending.get("review_evidence") or {})
    gw_evidence = dict(groundwork.get("evidence") or {})
    lineage = gw_evidence.get("fact_interpretation_hypothesis_lineage") if isinstance(gw_evidence.get("fact_interpretation_hypothesis_lineage"), dict) else {}

    discovery_learned = _text(review_evidence.get("summary") or review_evidence.get("analysis") or review_evidence.get("work_product"))
    buying_signals = _list_text(review_evidence.get("buying_signals")) or ([discovery_learned] if "proposal" in discovery_learned.casefold() or "advance" in discovery_learned.casefold() else [])
    objections = _list_text(review_evidence.get("objections") or review_evidence.get("risks") or review_evidence.get("evidence_gaps"))
    agreed_actions = _list_text(review_evidence.get("agreed_actions") or review_evidence.get("next_steps")) or ([pending.get("recommended_next_action")] if pending.get("recommended_next_action") else [])
    groundwork_hypotheses = _list_text(gw_evidence.get("growth_tension")) + _list_text(gw_evidence.get("provisional_opportunity"))

    evidence_gaps = _list_text(review_evidence.get("evidence_gaps")) + _list_text(gw_evidence.get("evidence_gaps"))
    assumptions = _list_text(lineage.get("hypothesis")) if lineage else []

    sources: list[dict[str, str]] = []
    for item in meeting_evidence.get("sources") or []:
        if isinstance(item, Mapping):
            sources.append({"kind": "discovery_meeting_evidence", "source_id": _text(item.get("source_id")), "location": _text(item.get("location"))})
    meeting_source_id = _text(meeting_evidence.get("source_id") or meeting_evidence.get("transcript_id") or meeting_evidence.get("drive_file_id"))
    if meeting_source_id and not sources:
        sources.append({"kind": "discovery_meeting_evidence", "source_id": meeting_source_id, "location": _text(meeting_evidence.get("source_url") or meeting_evidence.get("drive_web_view_link"))})
    for item in gw_evidence.get("source_backed_evidence") or gw_evidence.get("sources") or []:
        if isinstance(item, Mapping):
            sources.append({"kind": "groundwork_research_evidence", "source_id": _text(item.get("source_id") or item.get("url")), "location": _text(item.get("location") or item.get("url"))})
        elif _text(item):
            sources.append({"kind": "groundwork_research_evidence", "source_id": _text(item), "location": ""})
    sources.append({"kind": "groundwork_artefact", "source_id": f"{groundwork.get('canonical_run_id')}:v{groundwork.get('version')}", "location": ""})

    commercial_problem = _text(gw_evidence.get("growth_tension")) or discovery_learned
    desired_outcome = _text(gw_evidence.get("provisional_opportunity")) or _text(pending.get("recommended_next_action"))
    company = _text(pending.get("company")) or _text(pending.get("contact")) or "this prospect"
    recommended_fieldwork_scope = _text(review_evidence.get("recommended_scope")) or desired_outcome or "To be scoped by Claude from the evidence below; do not invent scope Tony has not been given."

    sections = {
        "what_was_learned_in_discovery": discovery_learned or "No discovery summary was recorded on the verified review evidence.",
        "groundwork_hypotheses_and_discovery_findings": {
            "groundwork_hypotheses": groundwork_hypotheses or ["No growth tension or provisional opportunity was recorded on the canonical Groundwork artefact."],
            "discovery_findings": [discovery_learned] if discovery_learned else [],
            "note": "Presented side by side; Tony has not reconciled or judged whether Discovery confirmed or changed these hypotheses.",
        },
        "commercial_problem": commercial_problem or "Not established by the evidence supplied.",
        "desired_outcome": desired_outcome or "Not established by the evidence supplied.",
        "buying_signals": buying_signals or ["None explicitly recorded; do not infer one."],
        "objections_and_risks": objections or ["None explicitly recorded."],
        "agreed_actions": agreed_actions or ["None explicitly recorded."],
        "evidence_gaps": evidence_gaps or ["None explicitly recorded; confirm with the client before assuming completeness."],
        "recommended_fieldwork_scope": recommended_fieldwork_scope,
        "assumptions": assumptions or ["None explicitly recorded."],
        "sources_and_lineage": sources,
    }

    commission = _render_commission(company, sections, groundwork)
    digest = hashlib.sha256(json.dumps(sections, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "brief_id": f"brief-{digest[:16]}",
        "company": company,
        "contact": _text(pending.get("contact")),
        "lead_id": _text(pending.get("lead_id")),
        "calendar_event_id": _text(pending.get("calendar_event_id")),
        "groundwork_canonical_run_id": _text(groundwork.get("canonical_run_id")),
        "groundwork_version": groundwork.get("version"),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "copyable_commission": commission,
        "digest": digest,
    }


def _render_commission(company: str, sections: Mapping[str, Any], groundwork: Mapping[str, Any]) -> str:
    gw_hyp = sections["groundwork_hypotheses_and_discovery_findings"]
    lines = [
        f"Commission: prepare a Narratiive proposal for {company}.",
        "",
        "You are drafting a commercial proposal from evidence Tony has already verified. Do not invent facts, "
        "evidence, client statements or sources beyond what is given below. Where evidence is missing, say so "
        "explicitly rather than filling it in.",
        "",
        f"What was learned in Discovery: {sections['what_was_learned_in_discovery']}",
        "",
        "Groundwork hypotheses (from pre-Discovery qualification, run " + str(groundwork.get("canonical_run_id")) + f" v{groundwork.get('version')}):",
        *[f"  - {item}" for item in gw_hyp["groundwork_hypotheses"]],
        "Discovery findings to compare against those hypotheses (confirm, update or replace them yourself — Tony has not pre-judged this):",
        *[f"  - {item}" for item in (gw_hyp["discovery_findings"] or ["(none explicitly recorded)"])],
        "",
        f"Commercial problem: {sections['commercial_problem']}",
        f"Desired outcome: {sections['desired_outcome']}",
        "Buying signals: " + "; ".join(sections["buying_signals"]),
        "Objections and risks: " + "; ".join(sections["objections_and_risks"]),
        "Agreed actions so far: " + "; ".join(sections["agreed_actions"]),
        "Evidence gaps: " + "; ".join(sections["evidence_gaps"]),
        f"Recommended Fieldwork scope: {sections['recommended_fieldwork_scope']}",
        "Assumptions: " + "; ".join(sections["assumptions"]),
        "",
        "Exact sources and lineage:",
        *[f"  - [{item['kind']}] {item['source_id']}" + (f" ({item['location']})" if item.get("location") else "") for item in sections["sources_and_lineage"]],
        "",
        "Produce the proposal only; do not send it, update any CRM, or claim it has been delivered. "
        "Matt will review and approve the exact resulting document before anything is sent.",
    ]
    return "\n".join(lines)
