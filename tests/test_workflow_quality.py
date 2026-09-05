from __future__ import annotations

import unittest

from runtime.workflow_quality import (
    discovery_preparation_quality_gate,
    growth_sprint_proposal_quality_gate,
    validate_operational_inputs,
)


def discovery_output() -> dict:
    return {
        "what_we_currently_believe": [
            {"statement": "The diagnostic reports unclear differentiation.", "classification": "fact", "evidence_refs": ["diagnostic:main_blockage"], "confidence": "high"},
            {"statement": "The current story may make comparison too easy.", "classification": "interpretation", "evidence_refs": ["blueprint:v1"], "confidence": "medium"},
            {"statement": "A sharper category entry point could improve demand quality.", "classification": "hypothesis", "evidence_refs": ["blueprint:v1"], "confidence": "low"},
        ],
        "discovery_hypotheses": [
            {"hypothesis": "Buyers struggle to distinguish the offer.", "basis": "Diagnostic blockage", "evidence_refs": ["diagnostic:main_blockage"], "validation_question": "Where do prospects compare this offer with alternatives?"},
            {"hypothesis": "Proof arrives too late in the journey.", "basis": "Blueprint tension", "evidence_refs": ["blueprint:v1"], "validation_question": "Which proof changes a hesitant buyers confidence fastest?"},
            {"hypothesis": "The strongest audience is too broadly defined.", "basis": "Evidence gap", "evidence_refs": ["blueprint:gap:audience"], "validation_question": "Which customer situation creates the greatest urgency today?"},
        ],
        "discovery_questions": [
            "Which customer situation creates the greatest urgency today?",
            "What makes a qualified buyer choose an alternative?",
            "Where does confidence break during the current journey?",
            "Which proof points consistently change a buyers mind?",
            "What strategic choice has the team avoided making?",
        ],
        "knowledge_gaps": ["Direct customer language remains unknown.", "Conversion evidence by audience remains unavailable."],
        "strategic_tensions": [
            {"tension": "Broad relevance versus distinctive meaning", "evidence_refs": ["blueprint:v1"]},
            {"tension": "Fast acquisition versus qualified demand", "evidence_refs": ["diagnostic:score"]},
        ],
        "suggested_meeting_objective": "Decide which growth assumption most urgently requires evidence before paid strategy begins.",
        "context_summary": "The synthetic diagnostic indicates a capable offer constrained by unclear differentiation, while the Blueprint Lite frames audience specificity and earlier proof as provisional opportunities that still require direct customer and commercial evidence.",
        "evidence_lineage": [
            {"claim": "Differentiation was the reported blockage.", "classification": "fact", "source_refs": ["diagnostic:main_blockage"]},
            {"claim": "Comparison may therefore be too easy.", "classification": "interpretation", "source_refs": ["blueprint:v1"]},
            {"claim": "A category entry point could improve demand.", "classification": "hypothesis", "source_refs": ["blueprint:v1"]},
        ],
        "external_action_taken": False,
    }


def proposal_output() -> dict:
    return {
        "discovery_synthesis": "The synthetic discovery evidence shows a team with a credible offer but no shared choice about the priority audience or the proof that moves that audience. The meeting confirmed urgency around demand quality while leaving customer language and competitive response uncertain and explicitly unresolved.",
        "growth_problem_or_opportunity": "Narratiive can help the team turn broad relevance into a distinctive, evidence-led growth choice that improves the quality of demand.",
        "why_further_strategic_work_is_justified": "The diagnostic and discovery expose connected questions across audience, category, positioning and proof. Resolving only the messaging symptom would leave the underlying commercial choices and evidence gaps untouched.",
        "proposed_scope": ["Audience and demand diagnosis", "Category and competitive research", "Positioning and narrative platform"],
        "workstreams_and_questions": [
            {"workstream": "Audience", "questions": ["Which customer situation produces the strongest commercial urgency?"]},
            {"workstream": "Category", "questions": ["Which category conventions make this offer seem interchangeable today?"]},
            {"workstream": "Positioning", "questions": ["Which defensible difference can organise the growth story clearly?"]},
        ],
        "expected_growth_blueprint_outputs": ["Market and category diagnosis", "Audience definition", "Growth barriers", "Positioning", "Narrative platform"],
        "commercial_proposal_inputs": {"timeline": "Four weeks", "investment_recommendation": "Within the authorised Growth Sprint range, exact figure for human approval", "human_approval_required": True, "approval_status": "pending"},
        "draft_client_communication": "Thank you for the candid discovery conversation. We heard a clear ambition to improve demand quality, alongside an unresolved choice about who matters most and which proof earns their confidence. We recommend a focused Growth Sprint spanning audience, category and positioning research, culminating in the Narratiive Growth Blueprint. The attached scope remains a draft for review, including timing, dependencies and a proposed investment that requires final human approval. If the framing reflects what you heard, the next step would be to review the scope together and resolve the remaining evidence questions before any work is commissioned.",
        "assumptions_and_dependencies": ["Access to existing customer evidence", "Availability of commercial stakeholders for interviews"],
        "evidence_lineage": [
            {"claim": "Demand quality is urgent.", "classification": "fact", "source_refs": ["meeting:notes:1"]},
            {"claim": "Positioning is the root problem.", "classification": "interpretation", "source_refs": ["meeting:notes:1", "blueprint:v1"]},
            {"claim": "A narrower audience will improve conversion.", "classification": "hypothesis", "source_refs": ["meeting:notes:1"]},
        ],
        "external_action_taken": False,
    }


class WorkflowQualityTests(unittest.TestCase):
    def test_discovery_preparation_requires_substance_lineage_and_uncertainty(self) -> None:
        result = discovery_preparation_quality_gate(discovery_output())
        self.assertTrue(result["passed"], result)

        weak = discovery_output()
        weak["discovery_questions"] = ["What matters?"] * 5
        weak["what_we_currently_believe"][2]["classification"] = "interpretation"
        result = discovery_preparation_quality_gate(weak)
        self.assertFalse(result["passed"])
        self.assertIn("five to ten high value questions", result["failed_checks"])
        self.assertIn("current beliefs are classified and sourced", result["failed_checks"])

    def test_proposal_requires_bounded_scope_lineage_and_pending_approval(self) -> None:
        result = growth_sprint_proposal_quality_gate(proposal_output())
        self.assertTrue(result["passed"], result)

        weak = proposal_output()
        weak["commercial_proposal_inputs"]["approval_status"] = "approved"
        weak["draft_client_communication"] = "Proposal sent to the client."
        result = growth_sprint_proposal_quality_gate(weak)
        self.assertFalse(result["passed"])
        self.assertIn("commercial inputs are pending human approval", result["failed_checks"])
        self.assertIn("no false external execution claim", result["failed_checks"])

    def test_discovery_evidence_ingestion_requires_source_provenance(self) -> None:
        valid = {
            "discovery_evidence": {
                "notes": "Synthetic meeting notes",
                "sources": [{"source_id": "meeting-1", "source_type": "notes", "location": "meeting:synthetic"}],
            },
            "blueprint_lite": "Synthetic blueprint",
            "commercial_context": {},
        }
        validate_operational_inputs("discovery_evidence_to_growth_sprint_proposal", valid)
        invalid = dict(valid)
        invalid["discovery_evidence"] = {"notes": "Unprovenanced notes"}
        with self.assertRaisesRegex(ValueError, "source provenance"):
            validate_operational_inputs("discovery_evidence_to_growth_sprint_proposal", invalid)


if __name__ == "__main__":
    unittest.main()
