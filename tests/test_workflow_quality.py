from __future__ import annotations

import unittest

from runtime.workflow_quality import (
    discovery_preparation_quality_gate,
    growth_blueprint_quality_gate,
    growth_sprint_proposal_quality_gate,
    research_evidence_quality_gate,
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


def growth_blueprint_output() -> dict:
    def section(label: str, evidence: str) -> dict:
        return {
            "diagnosis": f"The supplied evidence indicates that {label} is a material growth question whose current ambiguity constrains commercial choice and makes execution less coherent than the leadership ambition requires.",
            "evidence_refs": [evidence],
            "implication": f"Narratiive should make an explicit {label} choice before downstream activation is commissioned.",
            "uncertainties": [f"Direct validation of {label} remains incomplete."],
        }

    return {
        "market_category_diagnosis": section("market and category", "ev-1"),
        "audience": section("priority audience", "ev-2"),
        "growth_barriers": section("growth barriers", "ev-1"),
        "source_of_difference": section("source of difference", "ev-2"),
        "positioning": section("positioning", "ev-1"),
        "narrative": section("narrative platform", "ev-2"),
        "growth_opportunity": section("growth opportunity", "ev-1"),
        "activation_implications": section("activation implications", "ev-2"),
        "key_strategic_choices": [
            {"choice": "Prioritise the urgent audience", "tradeoff": "Reject broad relevance", "evidence_refs": ["ev-1"]},
            {"choice": "Lead with a category point of view", "tradeoff": "Reduce feature-led flexibility", "evidence_refs": ["ev-2"]},
            {"choice": "Use proof earlier", "tradeoff": "Simplify the opening story", "evidence_refs": ["ev-1", "ev-2"]},
        ],
        "evidence_and_uncertainty": ["Customer interviews remain limited.", "The competitor response is uncertain.", "Channel performance evidence is an open input."],
        "fact_interpretation_hypothesis_lineage": [
            {"claim": "The brief prioritises demand quality.", "classification": "fact", "source_refs": ["ev-1"]},
            {"claim": "Broad positioning is reducing choice.", "classification": "interpretation", "source_refs": ["ev-1", "ev-2"]},
            {"claim": "Earlier proof may improve conversion.", "classification": "hypothesis", "source_refs": ["ev-2"]},
        ],
        "evidence_lineage": [
            {"claim": "Demand quality is a stated priority.", "classification": "fact", "source_refs": ["ev-1"]},
            {"claim": "Category language is currently broad.", "classification": "fact", "source_refs": ["ev-2"]},
            {"claim": "Broad language weakens distinction.", "classification": "interpretation", "source_refs": ["ev-1", "ev-2"]},
            {"claim": "An urgent audience should lead.", "classification": "hypothesis", "source_refs": ["ev-1"]},
            {"claim": "Earlier proof may improve confidence.", "classification": "hypothesis", "source_refs": ["ev-2"]},
        ],
        "recommendation": "advance",
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

    def test_research_gate_requires_provenance_allocation_and_linked_findings(self) -> None:
        output = {
            "research_tasks": [{"task_id": "task-1", "question": "What matters?", "required_capability": "market_research", "assigned_worker": "narratiive-research-engine"}],
            "evidence_pack": {"records": [{"evidence_id": "ev-1"}], "sources": [{"policy": {"approved": True}}]},
            "source_provenance": [{"source_id": "source-1", "content_hash": "abc", "retrieved_at": "2026-09-05T00:00:00Z"}],
            "consolidated_findings": [{"statement": "Synthetic evidence", "classification": "fact", "evidence_refs": ["ev-1"], "source_refs": ["source-1"]}],
            "contradictions": [],
            "research_gaps": ["Customer evidence remains unavailable"],
            "further_research_requests": [{"gap": "Customer evidence", "status": "requires_additional_approved_source"}],
            "fact_interpretation_hypothesis_lineage": {"facts": [{"statement": "Synthetic evidence"}], "interpretations": [], "hypotheses": []},
            "external_action_taken": False,
        }
        self.assertTrue(research_evidence_quality_gate(output)["passed"])
        output["source_provenance"] = []
        self.assertFalse(research_evidence_quality_gate(output)["passed"])

    def test_source_publication_metadata_is_not_an_external_action_claim(self) -> None:
        output = growth_blueprint_output()
        output["evidence_lineage"][0]["published_at"] = "2026-09-05T00:00:00Z"

        self.assertTrue(growth_blueprint_quality_gate(output)["passed"])

        output["release_status"] = "Client-facing publication completed"
        self.assertFalse(growth_blueprint_quality_gate(output)["passed"])

    def test_growth_blueprint_gate_requires_substantive_strategy_and_lineage(self) -> None:
        output = growth_blueprint_output()
        self.assertTrue(growth_blueprint_quality_gate(output)["passed"])
        output["positioning"] = {"diagnosis": "Generic", "evidence_refs": [], "implication": "Do better", "uncertainties": []}
        self.assertFalse(growth_blueprint_quality_gate(output)["passed"])


if __name__ == "__main__":
    unittest.main()
