from __future__ import annotations

import unittest

from runtime.workflow_quality import (
    campaign_world_quality_gate,
    creative_bible_quality_gate,
    discovery_preparation_quality_gate,
    growth_blueprint_quality_gate,
    growth_sprint_proposal_quality_gate,
    research_evidence_quality_gate,
    validate_operational_inputs,
)


def _record(fields: tuple[str, ...], label: str = "Synthetic Northstar Test Co direction") -> dict:
    return {field: f"{label}: {field}" for field in fields}


def campaign_world_output() -> dict:
    territories = (
        "territory_name", "strategic_role", "audience_job", "key_message", "visual_direction",
        "copy_direction", "emotional_outcome", "example_activations", "channel_recommendations",
    )
    still = (
        "asset_name", "strategic_purpose", "channel", "creative_description", "sora_prompt",
        "recommended_dimensions", "notes",
    )
    motion = (
        "asset_name", "strategic_purpose", "channel", "duration", "creative_description",
        "shot_structure", "sora_prompt", "call_to_action", "notes",
    )
    social = ("creative_concept", "example_headline", "example_copy", "suggested_visual", "suggested_cta")
    channel = (
        "objective", "audience_behaviour", "content_role", "creative_adaptation",
        "recommended_asset_types", "measurement_focus",
    )
    return {
        "campaign_world": {
            "client_information": _record(("client_name", "industry", "category", "growth_blueprint_link", "date_created", "campaign_world_version")),
            "strategic_foundation": _record(("core_problem", "growth_opportunity", "strategic_positioning", "audience_summary", "core_narrative")),
            "creative_north_star": _record(("north_star_statement", "strategic_role", "emotional_job", "behavioural_change_required")),
            "visual_world": _record(("photography_style", "lighting_style", "colour_direction", "composition_style", "environment_style", "human_casting_style", "product_treatment", "typography_direction", "motion_direction", "brand_references")),
            "tone_of_voice": _record(("voice_description", "personality_traits", "words_to_use", "words_to_avoid", "cta_style", "headline_style", "caption_style", "email_style")),
            "campaign_territories": [_record(territories, f"Synthetic territory {index}") for index in range(3)],
            "still_image_generation_pack": [_record(still, f"Synthetic still {index}") for index in range(12)],
            "motion_generation_pack": [_record(motion, f"Synthetic motion {index}") for index in range(6)],
            "social_mockups": [
                {"platform": platform, **_record(social)}
                for platform in ("LinkedIn", "Instagram", "TikTok", "Facebook", "YouTube Shorts", "X")
            ],
            "channel_translation_framework": [
                {"channel": name, **_record(channel)}
                for name in ("Website", "Email", "LinkedIn", "Instagram", "TikTok", "Meta", "YouTube", "Search")
            ],
            "production_roadmap": _record(("priority_assets", "phase_1", "phase_2", "phase_3", "phase_4")),
        },
        "strategic_handoff": "Synthetic handoff; audience proof remains uncertain and requires validation.",
        "evidence_lineage": [
            {"claim": "Synthetic fact", "classification": "fact", "source_refs": ["blueprint:1"]},
            {"claim": "Synthetic interpretation", "classification": "interpretation", "source_refs": ["blueprint:1"]},
            {"claim": "Synthetic hypothesis", "classification": "hypothesis", "source_refs": ["blueprint:1"]},
        ],
        "external_action_taken": False,
    }


def creative_bible_output() -> dict:
    asset_types = (
        "hero_film", "launch_film", "thirty_second_advert", "fifteen_second_advert",
        "six_second_cutdown", "website_hero", "homepage_photography", "linkedin_campaign",
        "instagram_campaign", "tiktok_campaign", "youtube_campaign", "display_campaign",
        "outdoor", "email", "presentation", "podcast_artwork", "press_photography", "case_study_imagery",
    )
    image_fields = (
        "prompt_name", "purpose", "aspect_ratio", "subject", "environment", "lighting", "camera",
        "lens", "mood", "composition", "colour_palette", "prompt", "negative_prompt",
    )
    video_fields = (
        "prompt_name", "intended_tool", "duration", "scene_description", "camera_movement",
        "environment", "wardrobe", "performance_direction", "lighting", "lens", "audio",
        "editing_rhythm", "output_quality", "prompt", "negative_prompt",
    )
    scene = _record(("scene_number", "scene_description", "camera_notes", "lighting", "performance_direction", "transition"))
    bible = {
        "creative_north_star": _record(("campaign_name", "brand", "version", "date", "one_sentence_vision", "creative_ambition", "emotional_outcome", "human_truth", "narrative_tension")),
        "world_building": _record(("environment", "time", "weather", "geography", "architectural_language", "surface_language")),
        "visual_dna": {
            **_record(("photography_style", "lighting", "contrast", "depth", "composition")),
            "colour_palette": _record(("primary_colours", "accent_colours", "colours_to_avoid")),
        },
        "human_casting": _record(("demographics", "personality", "diversity", "expressions", "behaviour")),
        "wardrobe": _record(("wardrobe_direction", "texture", "colour_palette", "accessories", "footwear", "avoid")),
        "product_language": _record(("product_role", "product_behaviour", "product_context", "product_rules")),
        "camera_language": _record(("lens_choices", "camera_height", "movement", "framing", "pacing", "transitions", "camera_personality")),
        "motion_language": _record(("movement_principles", "motion_pacing", "use_of_stillness", "use_of_speed", "restrictions")),
        "sound_world": _record(("music", "ambient_sound", "voiceover", "silence", "rhythm", "natural_audio", "sonic_texture")),
        "editorial_principles": _record(("principles", "always", "never")),
        "campaign_asset_matrix": [
            {"asset_type": asset_type, **_record(("role", "audience", "message", "visual_direction", "format_notes", "production_notes"))}
            for asset_type in asset_types
        ],
        "storyboards": [
            {**_record(("asset_name", "objective", "audience", "narrative", "ending", "cta"), f"Synthetic storyboard {index}"), "scenes": [scene]}
            for index in range(3)
        ],
        "image_generation_pack": [_record(image_fields, f"Synthetic image prompt {index}") for index in range(20)],
        "video_generation_pack": [_record(video_fields, f"Synthetic video prompt {index}") for index in range(10)],
        "consistency_rules": _record(("universe_rules", "recurring_visual_cues", "recurring_behaviours", "recurring_sonic_cues", "brand_memory_devices")),
        "creative_quality_checklist": {"questions": [f"Synthetic quality question {index}?" for index in range(8)]},
        "creative_references_and_creative_taste": {
            **_record(("editorial_inspiration", "photography_characteristics", "film_characteristics", "design_characteristics", "atmosphere_vocabulary", "creative_reference_rule")),
            "creative_principles": _record(("always_include", "always_avoid")),
        },
        "production_handoff_summary": "Internal handoff only; approval remains pending.",
    }
    return {
        "message_system": _record(("promise", "proof", "call_to_action")),
        "tone": _record(("voice", "range", "guardrails")),
        "distinctive_assets": ["Synthetic signal", "Synthetic colour", "Synthetic behaviour"],
        "creative_principles": ["Human truth", "Specific detail", "Coherent world"],
        "formats": ["Still", "Motion", "Social"],
        "production_constraints": ["Human approval before production or publication"],
        "creative_directors_bible": bible,
        "external_action_taken": False,
    }


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

        denied = proposal_output()
        denied["draft_client_communication"] += " No email sent; this remains internal."
        self.assertTrue(growth_sprint_proposal_quality_gate(denied)["passed"])

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

    def test_fireflies_adapter_output_is_valid_discovery_evidence_without_inference(self) -> None:
        validate_operational_inputs(
            "discovery_evidence_to_growth_sprint_proposal",
            {
                "discovery_evidence": {
                    "transcript": "Synthetic: This is exact source meeting evidence.",
                    "fireflies_summary": {"action_items": ["Source-provided action only"]},
                    "sources": [{
                        "source_id": "fireflies:transcript:transcript-safe",
                        "source_type": "fireflies_transcript",
                        "location": "https://app.fireflies.ai/view/transcript-safe",
                        "content_hash": "safe-hash",
                    }],
                },
                "blueprint_lite": "Synthetic Blueprint Lite",
                "commercial_context": {},
            },
        )

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

    def test_campaign_world_gate_enforces_canonical_world_and_channel_coverage(self) -> None:
        output = campaign_world_output()
        self.assertTrue(campaign_world_quality_gate(output)["passed"])

        output["campaign_world"]["campaign_territories"] = output["campaign_world"]["campaign_territories"][:2]
        output["campaign_world"]["channel_translation_framework"] = [
            item for item in output["campaign_world"]["channel_translation_framework"] if item["channel"] != "Meta"
        ]
        result = campaign_world_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("three campaign territories are complete", result["failed_checks"])
        self.assertIn("channel translation covers canonical channels", result["failed_checks"])

    def test_campaign_world_gate_rejects_false_publication_claim(self) -> None:
        output = campaign_world_output()
        output["status_note"] = "Published to the client"
        result = campaign_world_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("no false external execution claim", result["failed_checks"])

    def test_creative_bible_gate_enforces_canonical_production_contract(self) -> None:
        output = creative_bible_output()
        self.assertTrue(creative_bible_quality_gate(output)["passed"])

        output["creative_directors_bible"]["image_generation_pack"] = output["creative_directors_bible"]["image_generation_pack"][:19]
        output["creative_directors_bible"]["storyboards"][0]["scenes"] = []
        result = creative_bible_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("twenty image prompts are complete", result["failed_checks"])
        self.assertIn("three storyboards are complete", result["failed_checks"])

    def test_creative_bible_gate_rejects_missing_taste_and_false_execution(self) -> None:
        output = creative_bible_output()
        output["creative_directors_bible"]["creative_references_and_creative_taste"] = {}
        output["release_note"] = "Publication completed"
        result = creative_bible_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("creative taste is attribute based", result["failed_checks"])
        self.assertIn("no false external execution claim", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
