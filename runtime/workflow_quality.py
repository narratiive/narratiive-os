from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


_FALSE_ACTION_MARKERS = (
    "email sent", "proposal sent", "sent to the client", "sent to the prospect",
    "meeting booked", "calendar event created", "notion updated", "published to the client",
    "client-facing publication completed", "publication completed",
)


def validate_operational_inputs(workflow_id: str, inputs: Mapping[str, Any]) -> None:
    """Validate evidence-bearing inputs before any specialist is dispatched."""
    if workflow_id == "blueprint_lite_to_discovery_preparation":
        if not _meaningful(inputs.get("blueprint_lite")):
            raise ValueError("discovery preparation requires a substantive Blueprint Lite")
        if not isinstance(inputs.get("diagnostic_evidence"), Mapping):
            raise ValueError("discovery preparation requires diagnostic evidence")
        if not isinstance(inputs.get("company_context"), Mapping):
            raise ValueError("discovery preparation requires company context")
    elif workflow_id == "discovery_evidence_to_growth_sprint_proposal":
        evidence = inputs.get("discovery_evidence")
        if not isinstance(evidence, Mapping):
            raise ValueError("Growth Sprint proposal preparation requires structured discovery evidence")
        if not any(_meaningful(evidence.get(key)) for key in ("notes", "transcript", "synthesis")):
            raise ValueError("discovery evidence requires notes, transcript or synthesis")
        sources = evidence.get("sources")
        if not isinstance(sources, list) or not sources or not all(_valid_source(item) for item in sources):
            raise ValueError("discovery evidence requires source provenance")
    elif workflow_id == "growth_sprint_to_research_engine":
        if not _meaningful(inputs.get("approved_growth_sprint_scope")):
            raise ValueError("research requires an approved Growth Sprint scope")
        if not _meaningful(inputs.get("research_requirements")):
            raise ValueError("research requires explicit research requirements")
        sources = inputs.get("research_sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("research requires approved sources")
        for source in sources:
            policy = source.get("policy") if isinstance(source, Mapping) and isinstance(source.get("policy"), Mapping) else {}
            if not isinstance(source, Mapping) or not all(_meaningful(source.get(key)) for key in ("source_id", "source_type")) or not _meaningful(source.get("uri") or source.get("location")) or policy.get("approved") is not True:
                raise ValueError("research sources must be complete and explicitly approved")
    elif workflow_id == "research_to_growth_blueprint":
        pack = inputs.get("evidence_pack")
        if not isinstance(pack, Mapping) or not _meaningful(pack.get("records")):
            raise ValueError("Growth Blueprint preparation requires a substantive evidence pack")
        if not _meaningful(inputs.get("approved_growth_sprint_scope")):
            raise ValueError("Growth Blueprint preparation requires approved Growth Sprint scope")


def discovery_preparation_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    beliefs = output.get("what_we_currently_believe")
    hypotheses = output.get("discovery_hypotheses")
    questions = output.get("discovery_questions")
    gaps = output.get("knowledge_gaps")
    tensions = output.get("strategic_tensions")
    lineage = output.get("evidence_lineage")
    checks = {
        "current_beliefs_are_classified_and_sourced": _classified_items(beliefs, minimum=3),
        "strategic_hypotheses_are_testable": _hypotheses(hypotheses),
        "knowledge_gaps_are_explicit": _meaningful_list(gaps, minimum=2),
        "strategic_tensions_are_evidence_linked": _evidence_linked_items(tensions, "tension", minimum=2),
        "five_to_ten_high_value_questions": _questions(questions, minimum=5, maximum=10),
        "meeting_objective_is_specific": _substantive_text(output.get("suggested_meeting_objective"), minimum_words=8),
        "diagnostic_and_blueprint_context_is_used": _substantive_text(output.get("context_summary"), minimum_words=20),
        "evidence_lineage_is_complete": _lineage(lineage, minimum=3),
        "uncertainty_is_preserved": _contains_uncertainty(output),
        "no_false_external_execution_claim": _no_false_action(output),
    }
    return _result(checks)


def growth_sprint_proposal_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    commercial = output.get("commercial_proposal_inputs")
    checks = {
        "discovery_synthesis_is_substantive": _substantive_text(output.get("discovery_synthesis"), minimum_words=35),
        "growth_problem_or_opportunity_is_clear": _substantive_text(output.get("growth_problem_or_opportunity"), minimum_words=15),
        "further_work_is_justified": _substantive_text(output.get("why_further_strategic_work_is_justified"), minimum_words=20),
        "scope_has_bounded_workstreams": _meaningful_list(output.get("proposed_scope"), minimum=3),
        "workstreams_have_strategic_questions": _workstreams(output.get("workstreams_and_questions")),
        "growth_blueprint_outputs_are_explicit": _meaningful_list(output.get("expected_growth_blueprint_outputs"), minimum=5),
        "commercial_inputs_are_pending_human_approval": _commercial_inputs(commercial),
        "assumptions_and_dependencies_are_explicit": _meaningful_list(output.get("assumptions_and_dependencies"), minimum=2),
        "draft_client_communication_is_reviewable": _bounded_text(output.get("draft_client_communication"), 60, 500),
        "evidence_lineage_is_complete": _lineage(output.get("evidence_lineage"), minimum=3),
        "no_false_external_execution_claim": _no_false_action(output),
    }
    return _result(checks)


def research_evidence_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    pack = output.get("evidence_pack")
    records = pack.get("records") if isinstance(pack, Mapping) else None
    checks = {
        "research_tasks_are_decomposed_and_allocated": _research_tasks(output.get("research_tasks")),
        "evidence_pack_contains_source_records": isinstance(records, list) and bool(records),
        "source_provenance_is_retained": _provenance(output.get("source_provenance")),
        "findings_are_evidence_linked": _research_findings(output.get("consolidated_findings")),
        "contradictions_are_explicit": isinstance(output.get("contradictions"), list),
        "research_gaps_are_explicit": isinstance(output.get("research_gaps"), list),
        "further_research_requests_are_explicit": isinstance(output.get("further_research_requests"), list),
        "fact_interpretation_hypothesis_classes_are_separate": _research_lineage(output.get("fact_interpretation_hypothesis_lineage")),
        "approved_source_policy_is_preserved": _approved_pack_sources(pack),
        "no_false_external_execution_claim": _no_false_action(output),
    }
    return _result(checks)


def growth_blueprint_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    strategic_fields = (
        "market_category_diagnosis", "audience", "growth_barriers", "source_of_difference",
        "positioning", "narrative", "growth_opportunity", "activation_implications",
    )
    checks = {
        "all_strategic_questions_are_substantive": all(_strategic_section(output.get(field)) for field in strategic_fields),
        "key_strategic_choices_are_explicit": _strategic_choices(output.get("key_strategic_choices")),
        "evidence_and_uncertainty_are_explicit": _meaningful_list(output.get("evidence_and_uncertainty"), minimum=3),
        "fact_interpretation_hypothesis_lineage_is_complete": _lineage(output.get("fact_interpretation_hypothesis_lineage"), minimum=3),
        "evidence_lineage_is_complete": _lineage(output.get("evidence_lineage"), minimum=5),
        "recommendation_is_advance": str(output.get("recommendation") or "").casefold() == "advance",
        "no_false_external_execution_claim": _no_false_action(output),
    }
    return _result(checks)


def _result(checks: Mapping[str, bool]) -> dict[str, Any]:
    failed = [name.replace("_", " ") for name, passed in checks.items() if not passed]
    return {"passed": not failed, "failed_checks": failed, "checks": dict(checks)}


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_meaningful(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_meaningful(item) for item in value)
    return value is not None


def _substantive_text(value: Any, *, minimum_words: int) -> bool:
    return isinstance(value, str) and len(value.split()) >= minimum_words


def _bounded_text(value: Any, minimum_words: int, maximum_words: int) -> bool:
    return isinstance(value, str) and minimum_words <= len(value.split()) <= maximum_words


def _meaningful_list(value: Any, *, minimum: int) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(_meaningful(item) for item in value)


def _valid_source(value: Any) -> bool:
    return isinstance(value, Mapping) and _meaningful(value.get("source_id")) and _meaningful(value.get("source_type")) and _meaningful(value.get("location"))


def _classified_items(value: Any, *, minimum: int) -> bool:
    allowed = {"fact", "interpretation", "hypothesis"}
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and all(
            isinstance(item, Mapping)
            and _meaningful(item.get("statement"))
            and str(item.get("classification") or "").casefold() in allowed
            and _meaningful_list(item.get("evidence_refs"), minimum=1)
            for item in value
        )
        and {str(item.get("classification") or "").casefold() for item in value} == allowed
    )


def _hypotheses(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 3
        and all(
            isinstance(item, Mapping)
            and _meaningful(item.get("hypothesis"))
            and _meaningful(item.get("basis"))
            and _meaningful_list(item.get("evidence_refs"), minimum=1)
            and str(item.get("validation_question") or "").strip().endswith("?")
            for item in value
        )
    )


def _evidence_linked_items(value: Any, field: str, *, minimum: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and all(isinstance(item, Mapping) and _meaningful(item.get(field)) and _meaningful_list(item.get("evidence_refs"), minimum=1) for item in value)
    )


def _questions(value: Any, *, minimum: int, maximum: int) -> bool:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        return False
    normalized = [" ".join(str(item).split()) for item in value]
    return all(len(item.split()) >= 5 and item.endswith("?") for item in normalized) and len({item.casefold() for item in normalized}) == len(normalized)


def _lineage(value: Any, *, minimum: int) -> bool:
    allowed = {"fact", "interpretation", "hypothesis"}
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and all(
            isinstance(item, Mapping)
            and _meaningful(item.get("claim"))
            and str(item.get("classification") or "").casefold() in allowed
            and _meaningful_list(item.get("source_refs"), minimum=1)
            for item in value
        )
        and {str(item.get("classification") or "").casefold() for item in value} == allowed
    )


def _workstreams(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 3
        and all(
            isinstance(item, Mapping)
            and _meaningful(item.get("workstream"))
            and _questions(item.get("questions"), minimum=1, maximum=6)
            for item in value
        )
    )


def _commercial_inputs(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and _meaningful(value.get("timeline"))
        and _meaningful(value.get("investment_recommendation"))
        and value.get("human_approval_required") is True
        and str(value.get("approval_status") or "").casefold() == "pending"
    )


def _research_tasks(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, Mapping)
        and _meaningful(item.get("task_id"))
        and _meaningful(item.get("question"))
        and item.get("required_capability") == "market_research"
        and _meaningful(item.get("assigned_worker"))
        for item in value
    )


def _provenance(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, Mapping)
        and _meaningful(item.get("source_id"))
        and _meaningful(item.get("content_hash"))
        and _meaningful(item.get("retrieved_at"))
        for item in value
    )


def _research_findings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, Mapping)
        and _meaningful(item.get("statement"))
        and item.get("classification") == "fact"
        and _meaningful_list(item.get("evidence_refs"), minimum=1)
        and _meaningful_list(item.get("source_refs"), minimum=1)
        for item in value
    )


def _research_lineage(value: Any) -> bool:
    return isinstance(value, Mapping) and all(isinstance(value.get(key), list) for key in ("facts", "interpretations", "hypotheses")) and bool(value.get("facts"))


def _approved_pack_sources(value: Any) -> bool:
    if not isinstance(value, Mapping) or not isinstance(value.get("sources"), list) or not value.get("sources"):
        return False
    return all(
        isinstance(source, Mapping)
        and isinstance(source.get("policy"), Mapping)
        and source["policy"].get("approved") is True
        for source in value["sources"]
    )


def _strategic_section(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and _substantive_text(value.get("diagnosis"), minimum_words=15)
        and _meaningful_list(value.get("evidence_refs"), minimum=1)
        and _substantive_text(value.get("implication"), minimum_words=8)
        and isinstance(value.get("uncertainties"), list)
    )


def _strategic_choices(value: Any) -> bool:
    return isinstance(value, list) and len(value) >= 3 and all(
        isinstance(item, Mapping)
        and _meaningful(item.get("choice"))
        and _meaningful(item.get("tradeoff"))
        and _meaningful_list(item.get("evidence_refs"), minimum=1)
        for item in value
    )


def _contains_uncertainty(output: Mapping[str, Any]) -> bool:
    rendered = json.dumps(dict(output), sort_keys=True).casefold()
    return any(term in rendered for term in ("unknown", "uncertain", "unanswered", "to validate", "hypothesis", "evidence gap"))


def _no_false_action(output: Mapping[str, Any]) -> bool:
    if output.get("external_action_taken") is True:
        return False
    rendered = json.dumps(dict(output), sort_keys=True).casefold()
    return not any(marker in rendered for marker in _FALSE_ACTION_MARKERS)
