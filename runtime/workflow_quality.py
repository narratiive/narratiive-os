from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from runtime.external_action_truth import no_asserted_external_action


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
    elif workflow_id == "growth_blueprint_to_campaign_world":
        if not isinstance(inputs.get("approved_growth_blueprint"), Mapping):
            raise ValueError("Campaign World preparation requires a structured approved Growth Blueprint")
        if not _lineage(inputs.get("evidence_lineage"), minimum=3):
            raise ValueError("Campaign World preparation requires complete evidence lineage")
        if not _meaningful(inputs.get("activation_implications")):
            raise ValueError("Campaign World preparation requires activation implications")
    elif workflow_id == "campaign_world_to_creative_bible":
        if not isinstance(inputs.get("approved_campaign_world"), Mapping):
            raise ValueError("Creative Director's Bible preparation requires a structured approved Campaign World")
        if not isinstance(inputs.get("growth_blueprint"), Mapping):
            raise ValueError("Creative Director's Bible preparation requires the structured Growth Blueprint")
        if not isinstance(inputs.get("production_context"), Mapping):
            raise ValueError("Creative Director's Bible preparation requires structured production context")


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


def growth_blueprint_deliverable_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the presentation handoff without treating rendering as approval."""
    qa = output.get("visual_qa")
    qa_checks = qa.get("checks") if isinstance(qa, Mapping) else {}
    checks = {
        "presentation_specification_is_present": _meaningful(output.get("presentation_specification")),
        "editable_pptx_is_present": _meaningful(output.get("editable_pptx")),
        "review_pdf_is_present": _meaningful(output.get("review_pdf")),
        "visual_qa_passed": isinstance(qa, Mapping) and qa.get("status") == "passed" and bool(qa_checks) and all(bool(item) for item in qa_checks.values()),
        "approval_is_pending": str(output.get("approval_status") or "pending") == "pending",
        "no_external_action_taken": output.get("external_action_taken") is False,
    }
    return _result(checks)


def campaign_world_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate a Campaign World against the canonical v1 creative contract."""
    world = output.get("campaign_world")
    checks = {
        "campaign_world_is_structured": isinstance(world, Mapping),
        "client_information_is_complete": _mapping_fields(
            _mapping_value(world, "client_information"),
            ("client_name", "industry", "category", "growth_blueprint_link", "date_created", "campaign_world_version"),
        ),
        "strategic_foundation_is_complete": _mapping_fields(
            _mapping_value(world, "strategic_foundation"),
            ("core_problem", "growth_opportunity", "strategic_positioning", "audience_summary", "core_narrative"),
        ),
        "creative_north_star_is_actionable": _mapping_fields(
            _mapping_value(world, "creative_north_star"),
            ("north_star_statement", "strategic_role", "emotional_job", "behavioural_change_required"),
        ),
        "visual_world_is_specific": _mapping_fields(
            _mapping_value(world, "visual_world"),
            (
                "photography_style", "lighting_style", "colour_direction", "composition_style",
                "environment_style", "human_casting_style", "product_treatment",
                "typography_direction", "motion_direction", "brand_references",
            ),
        ),
        "tone_of_voice_is_specific": _mapping_fields(
            _mapping_value(world, "tone_of_voice"),
            (
                "voice_description", "personality_traits", "words_to_use", "words_to_avoid",
                "cta_style", "headline_style", "caption_style", "email_style",
            ),
        ),
        "three_campaign_territories_are_complete": _records_with_fields(
            _mapping_value(world, "campaign_territories"),
            (
                "territory_name", "strategic_role", "audience_job", "key_message",
                "visual_direction", "copy_direction", "emotional_outcome",
                "example_activations", "channel_recommendations",
            ),
            minimum=3,
        ),
        "twelve_still_assets_are_production_ready": _records_with_fields(
            _mapping_value(world, "still_image_generation_pack"),
            (
                "asset_name", "strategic_purpose", "channel", "creative_description",
                "sora_prompt", "recommended_dimensions", "notes",
            ),
            minimum=12,
        ),
        "six_motion_assets_are_production_ready": _records_with_fields(
            _mapping_value(world, "motion_generation_pack"),
            (
                "asset_name", "strategic_purpose", "channel", "duration",
                "creative_description", "shot_structure", "sora_prompt", "call_to_action", "notes",
            ),
            minimum=6,
        ),
        "social_mockups_cover_canonical_platforms": _records_cover_values(
            _mapping_value(world, "social_mockups"),
            field="platform",
            required=("linkedin", "instagram", "tiktok", "facebook", "youtube shorts", "x"),
            fields=("creative_concept", "example_headline", "example_copy", "suggested_visual", "suggested_cta"),
        ),
        "channel_translation_covers_canonical_channels": _records_cover_values(
            _mapping_value(world, "channel_translation_framework"),
            field="channel",
            required=("website", "email", "linkedin", "instagram", "tiktok", "meta", "youtube", "search"),
            fields=("objective", "audience_behaviour", "content_role", "creative_adaptation", "recommended_asset_types", "measurement_focus"),
        ),
        "production_roadmap_is_phased": _mapping_fields(
            _mapping_value(world, "production_roadmap"),
            ("priority_assets", "phase_1", "phase_2", "phase_3", "phase_4"),
        ),
        "strategic_handoff_is_present": _meaningful(output.get("strategic_handoff")),
        "evidence_lineage_is_complete": _lineage(output.get("evidence_lineage"), minimum=3),
        "uncertainty_is_preserved": _contains_uncertainty(output),
        "no_false_external_execution_claim": _no_false_action(output),
    }
    return _result(checks)


def creative_bible_quality_gate(output: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the Creative Director's Bible v2 without inferring approval."""
    bible = output.get("creative_directors_bible")
    checks = {
        "message_system_is_present": _meaningful(output.get("message_system")),
        "tone_is_present": _meaningful(output.get("tone")),
        "distinctive_assets_are_explicit": _meaningful_list(output.get("distinctive_assets"), minimum=3),
        "creative_principles_are_explicit": _meaningful_list(output.get("creative_principles"), minimum=3),
        "formats_are_explicit": _meaningful_list(output.get("formats"), minimum=3),
        "production_constraints_are_explicit": isinstance(output.get("production_constraints"), list),
        "creative_bible_is_structured": isinstance(bible, Mapping),
        "creative_north_star_is_complete": _mapping_fields(
            _mapping_value(bible, "creative_north_star"),
            ("campaign_name", "brand", "version", "date", "one_sentence_vision", "creative_ambition", "emotional_outcome", "human_truth", "narrative_tension"),
        ),
        "world_building_is_complete": _mapping_fields(
            _mapping_value(bible, "world_building"),
            ("environment", "time", "weather", "geography", "architectural_language", "surface_language"),
        ),
        "visual_dna_is_complete": _visual_dna(_mapping_value(bible, "visual_dna")),
        "human_casting_is_complete": _mapping_fields(
            _mapping_value(bible, "human_casting"),
            ("demographics", "personality", "diversity", "expressions", "behaviour"),
        ),
        "wardrobe_is_complete": _mapping_fields(
            _mapping_value(bible, "wardrobe"),
            ("wardrobe_direction", "texture", "colour_palette", "accessories", "footwear", "avoid"),
        ),
        "product_language_is_complete": _mapping_fields(
            _mapping_value(bible, "product_language"),
            ("product_role", "product_behaviour", "product_context", "product_rules"),
        ),
        "camera_language_is_complete": _mapping_fields(
            _mapping_value(bible, "camera_language"),
            ("lens_choices", "camera_height", "movement", "framing", "pacing", "transitions", "camera_personality"),
        ),
        "motion_language_is_complete": _mapping_fields(
            _mapping_value(bible, "motion_language"),
            ("movement_principles", "motion_pacing", "use_of_stillness", "use_of_speed", "restrictions"),
        ),
        "sound_world_is_complete": _mapping_fields(
            _mapping_value(bible, "sound_world"),
            ("music", "ambient_sound", "voiceover", "silence", "rhythm", "natural_audio", "sonic_texture"),
        ),
        "editorial_principles_are_complete": _mapping_fields(
            _mapping_value(bible, "editorial_principles"), ("principles", "always", "never")
        ),
        "campaign_asset_matrix_is_complete": _asset_matrix(_mapping_value(bible, "campaign_asset_matrix")),
        "three_storyboards_are_complete": _storyboards(_mapping_value(bible, "storyboards")),
        "twenty_image_prompts_are_complete": _records_with_fields(
            _mapping_value(bible, "image_generation_pack"),
            ("prompt_name", "purpose", "aspect_ratio", "subject", "environment", "lighting", "camera", "lens", "mood", "composition", "colour_palette", "prompt", "negative_prompt"),
            minimum=20,
        ),
        "ten_video_prompts_are_complete": _records_with_fields(
            _mapping_value(bible, "video_generation_pack"),
            ("prompt_name", "intended_tool", "duration", "scene_description", "camera_movement", "environment", "wardrobe", "performance_direction", "lighting", "lens", "audio", "editing_rhythm", "output_quality", "prompt", "negative_prompt"),
            minimum=10,
        ),
        "consistency_rules_are_complete": _mapping_fields(
            _mapping_value(bible, "consistency_rules"),
            ("universe_rules", "recurring_visual_cues", "recurring_behaviours", "recurring_sonic_cues", "brand_memory_devices"),
        ),
        "creative_quality_checklist_is_usable": _creative_quality_checklist(
            _mapping_value(bible, "creative_quality_checklist")
        ),
        "creative_taste_is_attribute_based": _creative_taste(
            _mapping_value(bible, "creative_references_and_creative_taste")
        ),
        "production_handoff_summary_is_present": _meaningful(
            _mapping_value(bible, "production_handoff_summary")
        ),
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


def _mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _mapping_fields(value: Any, fields: tuple[str, ...]) -> bool:
    return isinstance(value, Mapping) and all(_meaningful(value.get(field)) for field in fields)


def _records_with_fields(value: Any, fields: tuple[str, ...], *, minimum: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and all(isinstance(item, Mapping) and all(_meaningful(item.get(field)) for field in fields) for item in value)
    )


def _records_cover_values(
    value: Any,
    *,
    field: str,
    required: tuple[str, ...],
    fields: tuple[str, ...],
) -> bool:
    if not _records_with_fields(value, (field, *fields), minimum=len(required)):
        return False
    observed = {str(item.get(field) or "").strip().casefold() for item in value}
    return set(required).issubset(observed)


def _visual_dna(value: Any) -> bool:
    if not _mapping_fields(
        value,
        ("photography_style", "colour_palette", "lighting", "contrast", "depth", "composition"),
    ):
        return False
    palette = value.get("colour_palette")
    return _mapping_fields(palette, ("primary_colours", "accent_colours", "colours_to_avoid"))


def _asset_matrix(value: Any) -> bool:
    required = {
        "hero_film", "launch_film", "thirty_second_advert", "fifteen_second_advert",
        "six_second_cutdown", "website_hero", "homepage_photography", "linkedin_campaign",
        "instagram_campaign", "tiktok_campaign", "youtube_campaign", "display_campaign",
        "outdoor", "email", "presentation", "podcast_artwork", "press_photography",
        "case_study_imagery",
    }
    if not isinstance(value, list) or len(value) < len(required):
        return False
    if not _records_with_fields(
        value,
        ("asset_type", "role", "audience", "message", "visual_direction", "format_notes", "production_notes"),
        minimum=len(required),
    ):
        return False
    return required.issubset({str(item.get("asset_type") or "").strip().casefold() for item in value})


def _storyboards(value: Any) -> bool:
    if not _records_with_fields(value, ("asset_name", "objective", "audience", "narrative", "scenes", "ending", "cta"), minimum=3):
        return False
    return all(
        _records_with_fields(
            item.get("scenes"),
            ("scene_number", "scene_description", "camera_notes", "lighting", "performance_direction", "transition"),
            minimum=1,
        )
        for item in value
    )


def _creative_quality_checklist(value: Any) -> bool:
    if isinstance(value, Mapping):
        value = value.get("questions")
    return _meaningful_list(value, minimum=8)


def _creative_taste(value: Any) -> bool:
    if not _mapping_fields(
        value,
        ("editorial_inspiration", "photography_characteristics", "film_characteristics", "design_characteristics", "creative_principles", "atmosphere_vocabulary", "creative_reference_rule"),
    ):
        return False
    principles = value.get("creative_principles")
    return _mapping_fields(principles, ("always_include", "always_avoid"))


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
    return no_asserted_external_action(output, _FALSE_ACTION_MARKERS)
