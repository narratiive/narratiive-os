from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from runtime.workflow_quality import campaign_world_quality_gate


class CampaignWorldTriageError(ValueError):
    pass


class CampaignWorldTriageWorker:
    """Apply Tony's bounded quality/taste triage without selecting for Matt."""

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "growth_blueprint_to_campaign_world":
            raise CampaignWorldTriageError("Campaign World triage received an unsupported workflow")
        candidates = contract.get("campaign_world_candidates")
        if not isinstance(candidates, list) or len(candidates) != 3:
            raise CampaignWorldTriageError("Tony triage requires exactly three Campaign World candidates")
        reviews = []
        ready = []
        revision = []
        signatures: set[str] = set()
        for item in candidates:
            if not isinstance(item, Mapping):
                raise CampaignWorldTriageError("Campaign World candidates must be structured objects")
            candidate_id = str(item.get("candidate_id") or "").strip()
            if not candidate_id:
                raise CampaignWorldTriageError("Campaign World candidate_id is required")
            quality = campaign_world_quality_gate(item)
            world = item.get("campaign_world") if isinstance(item.get("campaign_world"), Mapping) else {}
            signature = _creative_signature(world)
            distinct_from_other_routes = bool(signature) and signature not in signatures
            signatures.add(signature)
            taste_checks = {
                "strategically_coherent": _strategic_coherence(world),
                "visually_specific": _visual_specificity(world),
                "territories_are_distinct_and_ambitious": _territory_ambition(world),
                "channel_system_is_executable": _channel_executability(world),
                "distinct_from_other_candidates": distinct_from_other_routes,
            }
            quality_passed = quality.get("passed") is True
            forward = quality_passed and all(taste_checks.values())
            (ready if forward else revision).append(candidate_id)
            reviews.append({
                "candidate_id": candidate_id,
                "candidate_checksum": _checksum(item),
                "quality_verdict": "pass" if quality_passed else "revise",
                "quality_failed_checks": list(quality.get("failed_checks") or []),
                "tony_disposition": "forward" if forward else "return",
                "tony_rationale": (
                    "The candidate clears the structural, strategic, distinctiveness and execution bar; it is worth Matt's review."
                    if forward
                    else "Return for revision before Matt review: "
                    + ", ".join(name for name, passed in taste_checks.items() if not passed)
                ),
                "taste_checks": taste_checks,
            })
        selection_brief = {
            "selection_required": len(ready) >= 2,
            "human_selector": "matt",
            "auto_selection_authorised": False,
            "ready_candidate_ids": ready,
            "revision_candidate_ids": revision,
            "candidate_reviews": reviews,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        return {
            "campaign_world_reviews": reviews,
            "selection_brief": selection_brief,
            "external_action_taken": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }


def _checksum(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return len(value.split()) >= 3
    return bool(value)


def _strategic_coherence(world: Mapping[str, Any]) -> bool:
    foundation = world.get("strategic_foundation")
    north_star = world.get("creative_north_star")
    return isinstance(foundation, Mapping) and isinstance(north_star, Mapping) and all(
        _meaningful(value)
        for value in (
            foundation.get("core_problem"),
            foundation.get("growth_opportunity"),
            foundation.get("strategic_positioning"),
            north_star.get("north_star_statement"),
            north_star.get("behavioural_change_required"),
        )
    )


def _visual_specificity(world: Mapping[str, Any]) -> bool:
    visual = world.get("visual_world")
    if not isinstance(visual, Mapping):
        return False
    fields = (
        "photography_style", "lighting_style", "colour_direction", "composition_style",
        "environment_style", "human_casting_style", "product_treatment", "motion_direction",
    )
    values = [str(visual.get(field) or "").strip().casefold() for field in fields]
    generic = {"premium", "modern", "bold", "authentic", "engaging", "high quality"}
    return all(len(value.split()) >= 3 and value not in generic for value in values)


def _territory_ambition(world: Mapping[str, Any]) -> bool:
    territories = world.get("campaign_territories")
    if not isinstance(territories, list) or len(territories) < 3:
        return False
    names = {str(item.get("territory_name") or "").strip().casefold() for item in territories if isinstance(item, Mapping)}
    visuals = {str(item.get("visual_direction") or "").strip().casefold() for item in territories if isinstance(item, Mapping)}
    activations = [item.get("example_activations") for item in territories if isinstance(item, Mapping)]
    return len(names) == len(territories) and len(visuals) == len(territories) and all(
        isinstance(value, list) and len(value) >= 2 for value in activations
    )


def _channel_executability(world: Mapping[str, Any]) -> bool:
    roadmap = world.get("production_roadmap")
    channels = world.get("channel_translation_framework")
    return isinstance(roadmap, Mapping) and all(roadmap.get(key) for key in ("priority_assets", "phase_1", "phase_2")) and isinstance(channels, list) and len(channels) >= 8


def _creative_signature(world: Mapping[str, Any]) -> str:
    north_star = world.get("creative_north_star") if isinstance(world.get("creative_north_star"), Mapping) else {}
    territories = world.get("campaign_territories") if isinstance(world.get("campaign_territories"), list) else []
    values = [str(north_star.get("north_star_statement") or "").strip().casefold()]
    values.extend(str(item.get("territory_name") or "").strip().casefold() for item in territories if isinstance(item, Mapping))
    return "|".join(values)
