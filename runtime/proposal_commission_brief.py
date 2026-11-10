"""Build a copyable proposal commission brief from verified evidence only.

The brief combines the verified Discovery meeting evidence with the exact
canonical Groundwork artefact for the same engagement. It never invents a
business problem, outcome or scope: any field the upstream evidence does not
support is marked with an explicit placeholder rather than guessed.
"""

from __future__ import annotations

from typing import Any, Mapping

_PLACEHOLDER = "{{needs_input: not recorded in the verified evidence}}"


def _text(value: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return " ".join(item.split())
    return ""


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [" ".join(str(item).split()) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [" ".join(value.split())]
    return []


def build_commission_brief(pending: Mapping[str, Any], groundwork: Mapping[str, Any]) -> dict[str, Any]:
    meeting_evidence = pending.get("meeting_evidence") if isinstance(pending.get("meeting_evidence"), Mapping) else {}
    review_evidence = pending.get("review_evidence") if isinstance(pending.get("review_evidence"), Mapping) else {}
    company = str(pending.get("company") or "").strip() or "the prospect"
    contact = str(pending.get("contact") or "").strip()

    what_was_learned = _text(review_evidence, ("summary", "analysis", "work_product", "result")) or _PLACEHOLDER
    buying_signals = _list(review_evidence.get("buying_signal") or review_evidence.get("buying_signals")) or _list(
        [_text(review_evidence, ("buying_signal", "buying_signals", "positive_signal"))]
    )
    objections_and_risks = _list(review_evidence.get("objections_risks") or review_evidence.get("objections") or review_evidence.get("risks")) or [
        text for text in [_text(review_evidence, ("objections_risks", "objections", "risks"))] if text
    ]
    agreed_actions = _list(review_evidence.get("agreed_actions") or review_evidence.get("next_steps")) or [
        text for text in [_text(review_evidence, ("agreed_actions", "next_steps", "agreed_next_steps"))] if text
    ]
    evidence_gaps = _list(review_evidence.get("evidence_gaps"))
    recommended_next_action = str(pending.get("recommended_next_action") or "").strip() or _text(
        review_evidence, ("recommendation", "recommended_next_action", "next_action")
    ) or _PLACEHOLDER

    groundwork_hypotheses = _list(groundwork.get("hypotheses"))
    commercial_problem = _text(groundwork, ("commercial_problem", "hypothesis", "opportunity")) or (
        groundwork_hypotheses[0] if groundwork_hypotheses else _PLACEHOLDER
    )
    desired_outcome = _text(groundwork, ("desired_outcome", "intended_outcome")) or _PLACEHOLDER
    recommended_fieldwork_scope = _list(groundwork.get("recommended_fieldwork_scope") or groundwork.get("recommended_actions")) or [_PLACEHOLDER]
    assumptions = _list(groundwork.get("assumptions")) or [_PLACEHOLDER]

    hypotheses_status = (
        f"Groundwork recorded {len(groundwork_hypotheses)} hypothesis/es for {company}. Discovery evidence must be read "
        "against them directly; this brief does not auto-classify which were confirmed, changed or disproven — state that "
        "explicitly when commissioning the proposal."
        if groundwork_hypotheses
        else _PLACEHOLDER
    )

    sources: list[dict[str, Any]] = [
        {
            "source": "groundwork_artefact",
            "lineage": groundwork.get("source", ""),
            "canonical_run_id": groundwork.get("canonical_run_id", ""),
            "version": groundwork.get("version", ""),
        }
    ]
    evidence_source = str(meeting_evidence.get("evidence_source") or pending.get("evidence_source") or "").strip()
    sources.append(
        {
            "source": "discovery_meeting_evidence",
            "evidence_source": evidence_source,
            "transcript_id": str(meeting_evidence.get("transcript_id") or meeting_evidence.get("meeting_id") or ""),
            "drive_file_id": str(meeting_evidence.get("drive_file_id") or ""),
            "calendar_event_id": str(pending.get("calendar_event_id") or ""),
        }
    )

    brief = {
        "company": company,
        "contact": contact,
        "what_was_learned_in_discovery": what_was_learned,
        "groundwork_hypotheses_confirmed_or_changed": hypotheses_status,
        "groundwork_hypotheses": groundwork_hypotheses or [_PLACEHOLDER],
        "commercial_problem": commercial_problem,
        "desired_outcome": desired_outcome,
        "buying_signals": buying_signals or [_PLACEHOLDER],
        "objections_and_risks": objections_and_risks or [_PLACEHOLDER],
        "agreed_actions": agreed_actions or [_PLACEHOLDER],
        "evidence_gaps": evidence_gaps or [_PLACEHOLDER],
        "recommended_fieldwork_scope": recommended_fieldwork_scope,
        "assumptions": assumptions,
        "recommended_next_action": recommended_next_action,
        "sources_and_lineage": sources,
    }
    brief["copyable_claude_commission"] = _render_copyable(brief)
    return brief


def _render_copyable(brief: Mapping[str, Any]) -> str:
    def section(title: str, value: Any) -> str:
        if isinstance(value, list):
            body = "\n".join(f"- {item}" for item in value)
        else:
            body = str(value)
        return f"{title}:\n{body}"

    lines = [
        f"Proposal commission for {brief['company']}" + (f" ({brief['contact']})" if brief["contact"] else ""),
        "This commission is for drafting a Narratiive proposal only. It is not an approval to send, publish or commit "
        "externally. Distinguish fact, interpretation, hypothesis and open question in the draft; preserve this lineage.",
        "",
        section("What was learned in Discovery", brief["what_was_learned_in_discovery"]),
        "",
        section("Groundwork hypotheses on record", brief["groundwork_hypotheses"]),
        section("What changed or was confirmed versus Groundwork", brief["groundwork_hypotheses_confirmed_or_changed"]),
        "",
        section("Commercial problem", brief["commercial_problem"]),
        section("Desired outcome", brief["desired_outcome"]),
        "",
        section("Buying signals", brief["buying_signals"]),
        section("Objections and risks", brief["objections_and_risks"]),
        section("Agreed actions", brief["agreed_actions"]),
        section("Evidence gaps", brief["evidence_gaps"]),
        "",
        section("Recommended Fieldwork scope", brief["recommended_fieldwork_scope"]),
        section("Assumptions", brief["assumptions"]),
        section("Recommended next action", brief["recommended_next_action"]),
        "",
        "Exact sources and lineage:",
        "\n".join(f"- {entry}" for entry in [str(item) for item in brief["sources_and_lineage"]]),
        "",
        "Return the finished proposal to Tony for governed registration. Do not send, publish or represent this as "
        "agreed with the client until Matt has approved the exact registered version.",
    ]
    return "\n".join(lines)
