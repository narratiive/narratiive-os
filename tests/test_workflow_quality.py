from __future__ import annotations

import hashlib
import json
import unittest

from runtime.workflow_quality import (
    blueprint_director_quality_gate,
    campaign_world_candidates_quality_gate,
    campaign_world_quality_gate,
    campaign_world_triage_quality_gate,
    client_asset_delivery_quality_gate,
    creative_bible_quality_gate,
    creative_bible_triage_quality_gate,
    delivery_preparation_quality_gate,
    follow_up_preparation_quality_gate,
    discovery_preparation_quality_gate,
    growth_blueprint_quality_gate,
    growth_sprint_proposal_quality_gate,
    research_evidence_quality_gate,
    senior_strategist_review_quality_gate,
    strategic_synthesis_quality_gate,
    strategy_thesis_quality_gate,
    validate_operational_inputs,
)


def _record(fields: tuple[str, ...], label: str = "Synthetic Northstar Test Co direction") -> dict:
    return {field: f"{label}: {field}" for field in fields}


def campaign_identity() -> dict:
    return {
        "workspace_id": "agency",
        "client_id": "safe-client",
        "brand_id": "safe-brand",
        "market_ids": ["uk"],
        "product_ids": ["safe-product"],
        "campaign_id": "safe-campaign",
    }


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
            "campaign_territories": [
                {
                    **_record(territories, f"Synthetic territory {index}"),
                    "example_activations": [f"Synthetic activation {index}A", f"Synthetic activation {index}B"],
                }
                for index in range(3)
            ],
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


def campaign_world_candidates_output() -> dict:
    candidates = []
    for index, route in enumerate(("Radical intimacy", "Category rebellion", "Useful wonder"), start=1):
        item = campaign_world_output()
        item["candidate_id"] = f"northstar-world-{index}"
        item["route_name"] = route
        item["campaign_world"]["creative_north_star"]["north_star_statement"] = f"{route} makes the strategic choice unmistakable"
        for territory_index, territory in enumerate(item["campaign_world"]["campaign_territories"], start=1):
            territory["territory_name"] = f"{route} territory {territory_index}"
            territory["visual_direction"] = f"{route} visual language {territory_index} with specific material contrast"
        candidates.append(item)
    return {"campaign_world_candidates": candidates, "external_action_taken": False}


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
        "audience": {
            **section("priority audience", "ev-2"),
            "motivations": ["Make a confident high-stakes choice"],
            "tensions": ["Urgency conflicts with uncertainty"],
            "barriers": ["Broad language and late proof"],
            "triggers": ["A costly growth problem becomes unavoidable"],
            "behaviours": ["Seeks proof before entering a serious conversation"],
        },
        "growth_barriers": section("growth barriers", "ev-1"),
        "source_of_difference": section("source of difference", "ev-2"),
        "positioning": section("positioning", "ev-1"),
        "narrative": section("narrative platform", "ev-2"),
        "growth_opportunity": {
            **section("growth opportunity", "ev-1"),
            "commercial_consequence": "Improve qualified acquisition and conversion by concentrating relevance and presenting credible proof earlier in the buying journey.",
        },
        "activation_implications": section("activation implications", "ev-2"),
        "central_thesis": {
            "insight": "The real constraint is not awareness but the absence of a decisive commercial choice that makes proof relevant at the moment buyers need confidence.",
            "why_non_obvious": "The business appears to need more activity, yet the evidence indicates that more broadly framed activity would amplify ambiguity rather than create qualified demand.",
            "competitor_substitution_test": "A close competitor could not reuse this thesis because it depends on this company's documented broad positioning, late proof and urgent-buyer evidence pattern.",
            "commercial_consequence": "Concentrating relevance and moving proof earlier should improve qualified acquisition and conversion without assuming unknown client revenue or margin figures.",
            "evidence_refs": ["ev-1", "ev-2"],
        },
        "narrative_progression": [
            "Establish that activity volume is not the root constraint.",
            "Show how broad positioning prevents confident buyer choice.",
            "Identify the urgent audience situation and the proof it requires.",
            "Translate that choice into commercial and activation consequences.",
        ],
        "editorial_judgement": {
            "primary_emphasis": ["The decisive commercial choice and its evidence"],
            "supporting_evidence": ["Audience urgency and proof-timing evidence"],
            "remove_or_deprioritise": ["Generic channel lists and unsupported market sizing"],
        },
        "contradiction_resolution": {
            "unresolved_material_contradictions": [],
            "resolution_notes": ["The evidence, diagnosis and recommendation were checked for material contradiction."],
        },
        "quantitative_evidence_treatment": {
            "known_facts": [],
            "illustrative_or_directional": [],
            "unsourced_numbers_present": False,
        },
        "assumption_control": {
            "silent_guesses": False,
            "suppositions_labelled": True,
            "missing_evidence": ["Direct customer interviews remain limited."],
        },
        "completeness": {"materially_complete": True, "truncated": False},
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


def senior_strategist_review_output(checksum: str) -> dict:
    axes = (
        "strategic_coherence", "non_obviousness", "client_specificity",
        "evidence_support", "audience_insight", "commercial_consequence",
        "narrative_progression", "editorial_judgement", "activation_usefulness",
    )
    director_questions = (
        "non_obvious_central_thesis", "evidence_earns_conclusion",
        "progressively_more_specific", "every_major_section_advances_argument",
        "removable_material_identified", "competitor_substitution_resisted",
        "worth_paying_for", "meaningfully_reframes_founder_problem",
        "commercial_consequence_clear", "presentable_without_intellectual_rebuild",
    )
    return {
        "reference_standard": "Rave Coffee Growth Blueprint calibre, not content template",
        "senior_strategist_review": {
            axis: {
                "passed": True,
                "rationale": f"The synthetic candidate demonstrates sufficient {axis.replace('_', ' ')} through a specific cumulative argument grounded in the supplied evidence.",
                "evidence_refs": ["ev-1", "ev-2"],
            }
            for axis in axes
        },
        "director_judgement": {
            question: {
                "passed": True,
                "rationale": f"The synthetic candidate demonstrates {question.replace('_', ' ')} at credible senior strategy director calibre for this isolated test.",
            }
            for question in director_questions
        },
        "reviewed_blueprint_checksum": checksum,
        "review_disposition": "forward",
        "revision_instructions": [],
        "external_action_taken": False,
    }


def strategic_synthesis_output() -> dict:
    lineage = [
        {"claim": "Demand quality is a stated priority.", "classification": "fact", "source_refs": ["ev-1"]},
        {"claim": "Broad positioning weakens commercial choice.", "classification": "interpretation", "source_refs": ["ev-1", "ev-2"]},
        {"claim": "Earlier proof may improve qualified response.", "classification": "hypothesis", "source_refs": ["ev-2"]},
        {"claim": "Customer language is incomplete.", "classification": "fact", "source_refs": ["ev-2"]},
        {"claim": "A narrower entry point may concentrate demand.", "classification": "hypothesis", "source_refs": ["ev-1"]},
    ]
    return {
        "strategic_synthesis": {
            "executive_synthesis": "The supplied synthetic evidence consistently points to a credible offer constrained by broad positioning, insufficiently explicit audience priority and proof that arrives too late. The commercial problem is not a lack of possible activity but the absence of a shared growth choice. The next strategic stage should decide where demand can be concentrated without pretending unavailable customer evidence is known.",
            "commercial_problem": "Broad market relevance currently prevents the business from concentrating demand around one commercially urgent customer situation.",
            "growth_opportunity": "A narrower category entry point supported by earlier proof could improve qualified demand while preserving explicit validation requirements.",
            "implications": ["Choose one priority audience", "Make the category choice explicit", "Move credible proof earlier"],
        },
        "commercial_growth_equation": {
            "commercial_ambition": "Increase the proportion of demand that converts into commercially qualified opportunities.",
            "current_state": "The offer appears credible but its broad framing makes comparison and confident choice unnecessarily difficult.",
            "growth_gap": "The missing bridge is a distinctive position linked to an urgent audience situation and visible proof.",
            "growth_logic": "Concentrating relevance and proof should improve recognition, confidence and the quality of commercial response.",
            "growth_levers": ["Sharper audience priority", "Earlier evidence of value"],
            "assumptions": ["Direct customer validation remains incomplete"],
        },
        "evidence_patterns": [
            {"pattern": "Broad category language", "implication": "Make a deliberate category choice", "evidence_refs": ["ev-1"]},
            {"pattern": "Proof arrives late", "implication": "Move substantiation earlier", "evidence_refs": ["ev-2"]},
            {"pattern": "Audience priority is unclear", "implication": "Choose the urgent segment", "evidence_refs": ["ev-1", "ev-2"]},
        ],
        "strategic_tensions": [
            {"tension": "Broad relevance versus urgent specificity", "choice_required": "Choose the priority audience", "evidence_refs": ["ev-1"]},
            {"tension": "Category familiarity versus distinction", "choice_required": "Choose a defensible category frame", "evidence_refs": ["ev-2"]},
            {"tension": "Simple opening versus complete proof", "choice_required": "Sequence proof without overload", "evidence_refs": ["ev-1", "ev-2"]},
        ],
        "contradictions_and_gaps": ["Direct customer language remains unavailable"],
        "open_inputs": ["Validate the priority audience with customer evidence"],
        "fact_interpretation_hypothesis_lineage": lineage[:3],
        "evidence_lineage": lineage,
        "recommendation": "advance",
        "external_action_taken": False,
    }


def strategy_thesis_output() -> dict:
    synthesis = strategic_synthesis_output()
    return {
        "strategy_thesis": {
            "thesis_statement": "Growth should come from becoming the clearest credible choice for one urgent audience situation, rather than remaining broadly relevant to everyone.",
            "commercial_ambition": "Increase qualified demand and conversion by concentrating the company around a more decisive and provable market choice.",
            "growth_equation": "Sharper audience priority plus distinctive category framing plus earlier proof should create more confident and commercially valuable demand.",
            "priority_audience": "Prioritise buyers experiencing an urgent need for confidence and outcomes before they will enter a serious commercial conversation.",
            "category_choice": "Frame the offer around the commercially meaningful outcome rather than the broad service category currently used by competitors.",
            "source_of_difference": "Make evidence-led strategic clarity the organising difference, supported by visible proof rather than a longer list of capabilities.",
            "positioning_choice": "Position the company as the decisive route from an ambiguous growth problem to a credible, executable market choice.",
            "narrative_platform": "Move the audience from costly uncertainty through evidence-led choice to confidence about the next action worth taking.",
            "growth_opportunity": "Own the moment when an ambitious team needs to turn fragmented marketing activity into one coherent commercial growth system.",
            "activation_principles": "Lead with the urgent situation, make the strategic choice visible, introduce proof early and preserve every material uncertainty.",
        },
        "strategic_choices": [
            {"choice": "Prioritise the urgent audience", "tradeoff": "Reject undifferentiated reach", "evidence_refs": ["ev-1"]},
            {"choice": "Lead with an outcome frame", "tradeoff": "Reduce service-list flexibility", "evidence_refs": ["ev-2"]},
            {"choice": "Use proof earlier", "tradeoff": "Simplify the opening narrative", "evidence_refs": ["ev-1", "ev-2"]},
        ],
        "decision_register": [
            {"decision": "Approve the priority audience", "status": "requires_human_decision", "owner": "Matt", "evidence_refs": ["ev-1"]},
            {"decision": "Approve the category choice", "status": "proposed", "owner": "Matt", "evidence_refs": ["ev-2"]},
            {"decision": "Approve the narrative platform", "status": "requires_human_decision", "owner": "Matt", "evidence_refs": ["ev-1", "ev-2"]},
        ],
        "evidence_and_uncertainty": ["Customer interviews remain limited", "Competitor response is uncertain", "Channel performance remains an open input"],
        "fact_interpretation_hypothesis_lineage": synthesis["fact_interpretation_hypothesis_lineage"],
        "evidence_lineage": synthesis["evidence_lineage"],
        "recommendation": "advance",
        "external_action_taken": False,
    }


class WorkflowQualityTests(unittest.TestCase):
    def test_blueprint_director_output_is_client_facing_while_trace_stays_backstage(self) -> None:
        acts = ["Case", "Market", "Audience", "Positioning", "Growth", "Activation"]
        output = {
            "client_facing_blueprint": {
                "title": "Synthetic Client Growth Blueprint",
                "central_argument": "Synthetic Client can concentrate growth by becoming the clearest credible choice for one urgent buyer situation rather than broadening activity.",
                "pages": [
                    {
                        "page_number": index,
                        "act": acts[(index - 1) // 5],
                        "headline": f"Synthetic Client earns a sharper choice on page {index}",
                        "body": "This client-ready page advances one specific part of the cumulative strategic argument without exposing internal governance language.",
                        "commercial_consequence": "The choice concentrates demand and makes commercial response more likely.",
                        "visual_opportunity": "A concise comparison diagram showing the strategic shift.",
                        "visual_archetype": (
                            "cover", "thesis", "provocation", "question", "market_forces",
                            "comparison", "audience", "positioning", "roadmap", "measurement",
                        )[(index - 1) % 10],
                    }
                    for index in range(1, 31)
                ],
            },
            "editorial_trace": [
                {"page_number": index, "evidence_refs": ["ev-1"]}
                for index in range(1, 31)
            ],
            "external_action_taken": False,
        }
        self.assertTrue(blueprint_director_quality_gate(output)["passed"])
        output["client_facing_blueprint"]["pages"][0]["evidence_refs"] = ["ev-1"]
        result = blueprint_director_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("client copy excludes internal governance schema", result["failed_checks"])

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

    def test_senior_strategist_review_requires_every_axis_and_exact_disposition(self) -> None:
        output = senior_strategist_review_output("a" * 64)
        self.assertTrue(senior_strategist_review_quality_gate(output)["passed"])
        output["senior_strategist_review"]["client_specificity"]["passed"] = False
        output["review_disposition"] = "revise"
        output["revision_instructions"] = ["Make the opportunity client-specific."]
        self.assertFalse(senior_strategist_review_quality_gate(output)["passed"])

    def test_strategic_synthesis_preserves_evidence_and_cannot_claim_external_action(self) -> None:
        output = strategic_synthesis_output()
        self.assertTrue(strategic_synthesis_quality_gate(output)["passed"])
        output["strategic_tensions"][0]["evidence_refs"] = []
        output["external_action_taken"] = True
        result = strategic_synthesis_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("strategic tensions are explicit", result["failed_checks"])
        self.assertIn("no false external execution claim", result["failed_checks"])

    def test_strategy_thesis_keeps_decisions_pending_for_matt(self) -> None:
        output = strategy_thesis_output()
        self.assertTrue(strategy_thesis_quality_gate(output)["passed"])
        output["decision_register"][0]["owner"] = "Tony"
        result = strategy_thesis_quality_gate(output)
        self.assertFalse(result["passed"])
        self.assertIn("decision register preserves human authority", result["failed_checks"])

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

    def test_campaign_world_candidate_and_triage_gates_require_real_human_choice(self) -> None:
        generated = campaign_world_candidates_output()
        self.assertTrue(campaign_world_candidates_quality_gate(generated)["passed"])
        reviews = [{
            "candidate_id": item["candidate_id"],
            "candidate_checksum": f"checksum-{index}",
            "quality_verdict": "pass",
            "tony_disposition": "forward",
            "tony_rationale": "This route is strategically coherent, distinctive and executable.",
            "taste_checks": {"specific": True},
        } for index, item in enumerate(generated["campaign_world_candidates"], start=1)]
        triage = {
            "campaign_world_reviews": reviews,
            "selection_brief": {
                "selection_required": True,
                "human_selector": "matt",
                "auto_selection_authorised": False,
                "ready_candidate_ids": [item["candidate_id"] for item in generated["campaign_world_candidates"]],
            },
            "publication_authorised": False,
            "media_spend_authorised": False,
            "external_action_taken": False,
        }
        self.assertTrue(campaign_world_triage_quality_gate(triage)["passed"])
        triage["selection_brief"]["auto_selection_authorised"] = True
        self.assertFalse(campaign_world_triage_quality_gate(triage)["passed"])

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

    def test_creative_bible_triage_gate_requires_tony_forward_and_matt_control(self) -> None:
        output = {
            "creative_bible_review": {
                "reviewed_bible_checksum": "safe-checksum",
                "tony_disposition": "forward",
                "tony_rationale": "Ready for exact human review.",
                "taste_checks": {"coherent": True, "producible": True},
                "taste_is_advisory": True,
                "approval_granted": False,
            },
            "creative_bible_approval_brief": {
                "requires_matt": True,
                "creative_bible_checksum": "safe-checksum",
                "auto_approval_authorised": False,
            },
            "production_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
            "external_action_taken": False,
        }
        self.assertTrue(creative_bible_triage_quality_gate(output)["passed"])
        output["creative_bible_approval_brief"]["auto_approval_authorised"] = True
        self.assertFalse(creative_bible_triage_quality_gate(output)["passed"])

    def test_asset_production_requires_exact_matt_approved_creative_bible(self) -> None:
        bible = creative_bible_output()["creative_directors_bible"]
        checksum = hashlib.sha256(
            json.dumps(bible, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        inputs = {
            "campaign_identity": campaign_identity(),
            "approved_creative_bible": bible,
            "creative_bible_approval": {
                "decision": "creative_bible_approval",
                "approver": "telegram:matt",
                "creative_bible_checksum": checksum,
            },
            "asset_manifest": {"manifest_id": "safe-manifest"},
            "production_constraints": ["No publication without approval"],
        }
        validate_operational_inputs("creative_bible_to_asset_production", inputs)
        inputs["creative_bible_approval"]["creative_bible_checksum"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "exact Creative Bible checksum"):
            validate_operational_inputs("creative_bible_to_asset_production", inputs)

    def test_delivery_preparation_requires_exact_matt_approved_asset_versions(self) -> None:
        suite_checksum = "a" * 64
        inputs = {
            "campaign_identity": campaign_identity(),
            "reviewed_assets": [
                {
                    "asset_version_id": "safe-asset-v1",
                    "status": "approved",
                    "approval_status": "approved",
                    "source_asset_suite_checksum": suite_checksum,
                }
            ],
            "asset_suite_approval": {
                "decision": "asset_suite_approval",
                "approver": "telegram:matt",
                "asset_suite_checksum": suite_checksum,
                "asset_version_ids": ["safe-asset-v1"],
            },
            "asset_manifest": {"manifest_id": "safe-manifest"},
            "delivery_requirements": {"destination": "client Drive delivery folder"},
        }
        validate_operational_inputs("asset_review_to_delivery_preparation", inputs)
        inputs["reviewed_assets"][0]["asset_version_id"] = "unapproved-version"
        with self.assertRaisesRegex(ValueError, "exact approved version IDs"):
            validate_operational_inputs("asset_review_to_delivery_preparation", inputs)

    def test_delivery_preparation_quality_requires_a_non_executing_exact_action_preview(self) -> None:
        asset = {
            "asset_version_id": "safe-asset-v1",
            "asset_id": "safe-asset",
            "production_job_id": "safe-job",
            "file_checksum": "a" * 64,
            "drive_uri": "drive://safe/safe-asset-v1",
            "source_asset_suite_checksum": "b" * 64,
            "status": "ready_for_delivery_approval",
        }
        output = {
            "delivery_package": {
                "delivery_package_id": "safe-package",
                "checksum": "c" * 64,
                "source_asset_manifest_id": "safe-manifest",
                "source_asset_manifest_checksum": "d" * 64,
                "source_asset_suite_checksum": "b" * 64,
                "status": "prepared_for_human_approval",
                "assets": [asset],
            },
            "delivery_manifest": {"asset_count": 1, "assets": [asset]},
            "proposed_delivery_action": {
                "action_type": "client_asset_delivery",
                "status": "pending_human_approval",
                "requires_human_approval": True,
                "execution_authorised": False,
                "delivery_package_checksum": "c" * 64,
            },
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
            "external_action_taken": False,
        }
        self.assertTrue(delivery_preparation_quality_gate(output)["passed"])
        output["proposed_delivery_action"]["execution_authorised"] = True
        self.assertFalse(delivery_preparation_quality_gate(output)["passed"])

    def test_client_delivery_quality_requires_verified_receipt_without_publication_or_spend(self) -> None:
        output = {
            "verified_delivery_evidence": {
                "delivery_package_id": "safe-package",
                "delivery_package_checksum": "a" * 64,
                "destination": "safe client Drive folder",
                "delivered_at": "2026-09-19T12:00:00Z",
                "delivered_asset_version_ids": ["safe-asset-v1"],
            },
            "delivery_receipt": {
                "receipt_id": "safe-receipt",
                "delivery_package_checksum": "a" * 64,
                "status": "delivered",
            },
            "external_action_taken": True,
            "delivery_authorised": True,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        self.assertTrue(client_asset_delivery_quality_gate(output)["passed"])
        output["media_spend_authorised"] = True
        self.assertFalse(client_asset_delivery_quality_gate(output)["passed"])

    def test_follow_up_quality_preserves_human_strategy_and_read_only_media_control(self) -> None:
        output = {
            "recommended_follow_up": "Confirm client access and review verified campaign performance after the agreed observation window.",
            "measurement_actions": [
                "Confirm tracking health before interpreting campaign outcomes.",
                "Ingest provider performance through read only normalisation.",
                "Map provider creative IDs to exact Narratiive versions.",
                "Prepare evidence graded insights for human approval.",
            ],
            "draft_client_communication": "The approved suite has been delivered for your review. We will assess verified performance after the agreed observation window and return any proposed creative iteration for your approval before further production or publication.",
            "performance_ingestion_plan": {
                "campaign_id": "safe-campaign",
                "asset_version_ids": ["safe-asset-v1"],
                "providers": ["meta", "tiktok", "google"],
                "mode": "read_only_normalised_ingestion",
                "tracking_must_be_verified": True,
                "provider_mapping_required": True,
            },
            "iteration_control": {
                "tony_role": "orchestrate_monitor_and_quality_check",
                "strategy_authority": "human",
                "insight_requires_evidence": True,
                "creative_iteration_requires_human_approval": True,
                "autonomous_publication_authorised": False,
                "autonomous_media_spend_authorised": False,
            },
            "external_action_taken": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        self.assertTrue(follow_up_preparation_quality_gate(output)["passed"])
        output["iteration_control"]["strategy_authority"] = "tony"
        self.assertFalse(follow_up_preparation_quality_gate(output)["passed"])

    def test_campaign_workflows_require_complete_stable_identity(self) -> None:
        inputs = {
            "approved_growth_blueprint": {"status": "approved"},
            "evidence_lineage": campaign_world_output()["evidence_lineage"],
            "activation_implications": {"priority": "Synthetic"},
        }
        with self.assertRaisesRegex(ValueError, "campaign_identity"):
            validate_operational_inputs("growth_blueprint_to_campaign_world", inputs)
        inputs["campaign_identity"] = campaign_identity()
        validate_operational_inputs("growth_blueprint_to_campaign_world", inputs)
        inputs["campaign_identity"]["market_ids"] = []
        with self.assertRaisesRegex(ValueError, "market_ids"):
            validate_operational_inputs("growth_blueprint_to_campaign_world", inputs)


if __name__ == "__main__":
    unittest.main()
