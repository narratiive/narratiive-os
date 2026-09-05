from __future__ import annotations


_INSTRUCTIONS = {
    "blueprint_lite_to_discovery_preparation": """
Prepare an internal Discovery Preparation grounded in the supplied Growth Diagnostic evidence and approved Blueprint Lite. Return top-level JSON fields exactly as requested. what_we_currently_believe must contain at least three objects with statement, classification (fact, interpretation or hypothesis), evidence_refs and confidence. discovery_hypotheses must contain at least three objects; every object must include a substantive hypothesis, its evidence-grounded basis, one or more evidence_refs, and a full validation_question ending with a question mark (?). strategic_tensions must contain at least two objects with tension and evidence_refs. evidence_lineage must contain claim, classification and source_refs objects. Include 5–10 distinct, high-value discovery questions, explicit knowledge gaps, a substantive context_summary and one specific suggested_meeting_objective. Preserve unanswered questions and uncertainty. This is internal preparation: do not book a meeting, send anything, update a CRM or claim those actions occurred.
""",
    "discovery_evidence_to_growth_sprint_proposal": """
Prepare an internal, bespoke Growth Sprint proposal package grounded only in the supplied Discovery evidence, Blueprint Lite and commercial context. Return top-level JSON fields exactly as requested. Include a substantive discovery_synthesis; a clear growth_problem_or_opportunity; why_further_strategic_work_is_justified; at least three bounded proposed_scope items; expected_growth_blueprint_outputs; and assumptions_and_dependencies. workstreams_and_questions must contain at least three objects; every object must use the exact key workstream and the exact key questions, whose value is a list of 1–6 distinct, substantive questions each ending with a question mark (?). evidence_lineage must contain at least three objects with the exact keys claim, classification and source_refs, and the classification value must be exactly fact, interpretation or hypothesis with all three classifications represented; put synthetic or uncertainty qualifications in the claim, not in the classification value. commercial_proposal_inputs must contain timeline, investment_recommendation, human_approval_required=true and approval_status=pending. draft_client_communication must be a single plain JSON string of 60–500 words, not an object; clearly mark it as a draft for human review. Do not send it, update Notion, accept commercial terms or claim any external action occurred.
""",
    "research_to_growth_blueprint": """
Prepare an internal Growth Blueprint strategic draft from the approved Growth Sprint scope and the supplied evidence pack. Return every requested top-level field. Each strategic section (market_category_diagnosis, audience, growth_barriers, source_of_difference, positioning, narrative, growth_opportunity and activation_implications) must be an object with a substantive diagnosis, evidence_refs, a commercially useful implication and an uncertainties list. Include at least three key_strategic_choices with choice, tradeoff and evidence_refs. fact_interpretation_hypothesis_lineage must be a list of at least three claim-level objects using the exact keys claim, classification and source_refs; classification must be exactly fact, interpretation or hypothesis, and all three classifications must be represented. evidence_lineage must be a list of at least five objects using those same exact keys and classification values. evidence_and_uncertainty must be a list of at least three substantive statements collectively covering contradictions, evidence limits and open inputs; do not return an object for this field. recommendation must be the exact JSON string "advance" only when this internal draft is genuinely ready for human review, otherwise use the exact string "revise" or "stop". Preserve caveats in the relevant claim or uncertainty statement rather than changing machine field shapes. Do not claim canonical approval, client release, presentation export or any external action.
""",
}


def workflow_instruction(workflow_id: str, stage_id: str, expected_outputs: tuple[str, ...]) -> str:
    base = (
        f"Prepare the internal work for workflow {workflow_id} step {stage_id}. "
        f"Return these required top-level fields: {', '.join(expected_outputs)}."
    )
    specific = _INSTRUCTIONS.get(workflow_id, "")
    return f"{base}\n{specific.strip()}" if specific else base
