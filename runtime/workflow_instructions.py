from __future__ import annotations


_INSTRUCTIONS = {
    "blueprint_lite_to_discovery_preparation": """
Prepare an internal Discovery Preparation grounded in the supplied Growth Diagnostic evidence and approved Blueprint Lite. Return top-level JSON fields exactly as requested. what_we_currently_believe must contain at least three objects with statement, classification (fact, interpretation or hypothesis), evidence_refs and confidence. discovery_hypotheses must contain at least three objects with hypothesis, basis, evidence_refs and validation_question. strategic_tensions must contain at least two objects with tension and evidence_refs. evidence_lineage must contain claim, classification and source_refs objects. Include 5–10 distinct, high-value discovery questions, explicit knowledge gaps, a substantive context_summary and one specific suggested_meeting_objective. Preserve unanswered questions and uncertainty. This is internal preparation: do not book a meeting, send anything, update a CRM or claim those actions occurred.
""",
    "discovery_evidence_to_growth_sprint_proposal": """
Prepare an internal, bespoke Growth Sprint proposal package grounded only in the supplied Discovery evidence, Blueprint Lite and commercial context. Return top-level JSON fields exactly as requested. Include a substantive discovery_synthesis; a clear growth_problem_or_opportunity; why_further_strategic_work_is_justified; at least three bounded proposed_scope items; workstreams_and_questions objects; expected_growth_blueprint_outputs; assumptions_and_dependencies; and evidence_lineage objects with claim, classification and source_refs. commercial_proposal_inputs must contain timeline, investment_recommendation, human_approval_required=true and approval_status=pending. draft_client_communication is a reviewable draft only. Do not send it, update Notion, accept commercial terms or claim any external action occurred.
""",
}


def workflow_instruction(workflow_id: str, stage_id: str, expected_outputs: tuple[str, ...]) -> str:
    base = (
        f"Prepare the internal work for workflow {workflow_id} step {stage_id}. "
        f"Return these required top-level fields: {', '.join(expected_outputs)}."
    )
    specific = _INSTRUCTIONS.get(workflow_id, "")
    return f"{base}\n{specific.strip()}" if specific else base
