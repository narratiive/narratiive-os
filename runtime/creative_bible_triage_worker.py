from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


class CreativeBibleTriageError(ValueError):
    pass


class CreativeBibleTriageWorker:
    """Apply Tony's bounded creative-director review without granting approval."""

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "campaign_world_to_creative_bible":
            raise CreativeBibleTriageError("Creative Bible triage received an unsupported workflow")
        bible = contract.get("creative_directors_bible")
        if not isinstance(bible, Mapping):
            raise CreativeBibleTriageError("Tony triage requires a structured Creative Director's Bible")

        checks = {
            "creative_north_star_is_decisive": _section_complete(
                bible,
                "creative_north_star",
                ("one_sentence_vision", "creative_ambition", "emotional_outcome", "human_truth", "narrative_tension"),
            ),
            "world_is_visually_coherent": all(
                _section_complete(bible, section, fields)
                for section, fields in (
                    ("world_building", ("environment", "architectural_language", "surface_language")),
                    ("camera_language", ("lens_choices", "movement", "framing", "camera_personality")),
                    ("motion_language", ("movement_principles", "motion_pacing", "restrictions")),
                    ("sound_world", ("music", "voiceover", "rhythm", "sonic_texture")),
                )
            ),
            "distinctive_system_is_repeatable": _distinctive_system(contract, bible),
            "asset_system_is_producible": _asset_system_is_producible(bible),
            "production_guardrails_are_explicit": _meaningful_list(contract.get("production_constraints"), minimum=1)
            and _meaningful(bible.get("production_handoff_summary")),
            "no_publication_or_spend_authority": contract.get("publication_authorised") is not True
            and contract.get("media_spend_authorised") is not True
            and contract.get("external_action_taken") is not True,
        }
        forward = all(checks.values())
        failed = [name for name, passed in checks.items() if not passed]
        checksum = _checksum(bible)
        review = {
            "reviewed_bible_checksum": checksum,
            "tony_disposition": "forward" if forward else "return",
            "tony_rationale": (
                "The Bible is strategically coherent, distinctive, repeatable and sufficiently explicit for Matt's exact-version review."
                if forward
                else "Return for revision before Matt review: " + ", ".join(failed)
            ),
            "taste_checks": checks,
            "taste_is_advisory": True,
            "approval_granted": False,
        }
        return {
            "creative_bible_review": review,
            "creative_bible_approval_brief": {
                "requires_matt": forward,
                "creative_bible_checksum": checksum,
                "tony_disposition": review["tony_disposition"],
                "auto_approval_authorised": False,
                "production_authorised": False,
                "publication_authorised": False,
                "media_spend_authorised": False,
            },
            "external_action_taken": False,
            "production_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }


def _checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return len(value.split()) >= 2
    if isinstance(value, Mapping):
        return bool(value) and all(_meaningful(item) for item in value.values())
    if isinstance(value, list):
        return bool(value) and all(_meaningful(item) for item in value)
    return value is not None


def _meaningful_list(value: Any, *, minimum: int) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(_meaningful(item) for item in value)


def _section_complete(bible: Mapping[str, Any], section: str, fields: tuple[str, ...]) -> bool:
    value = bible.get(section)
    return isinstance(value, Mapping) and all(_meaningful(value.get(field)) for field in fields)


def _distinctive_system(contract: Mapping[str, Any], bible: Mapping[str, Any]) -> bool:
    assets = contract.get("distinctive_assets")
    rules = bible.get("consistency_rules")
    taste = bible.get("creative_references_and_creative_taste")
    return (
        _meaningful_list(assets, minimum=3)
        and isinstance(rules, Mapping)
        and all(_meaningful(rules.get(field)) for field in ("universe_rules", "recurring_visual_cues", "brand_memory_devices"))
        and isinstance(taste, Mapping)
        and all(
            _meaningful(taste.get(field))
            for field in ("photography_characteristics", "film_characteristics", "design_characteristics", "creative_reference_rule")
        )
    )


def _asset_system_is_producible(bible: Mapping[str, Any]) -> bool:
    matrix = bible.get("campaign_asset_matrix")
    storyboards = bible.get("storyboards")
    image_pack = bible.get("image_generation_pack")
    video_pack = bible.get("video_generation_pack")
    return (
        isinstance(matrix, list)
        and len(matrix) >= 18
        and isinstance(storyboards, list)
        and len(storyboards) >= 3
        and isinstance(image_pack, list)
        and len(image_pack) >= 20
        and isinstance(video_pack, list)
        and len(video_pack) >= 10
    )
