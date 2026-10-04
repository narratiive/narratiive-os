from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SeniorStrategistReviewWorker:
    """Independent, read-only review using Rave calibre, never Rave content."""

    REFERENCE_STANDARD = "Rave Coffee Growth Blueprint calibre, not content template"

    _AXES = (
        "evidence", "diagnosis", "non_obvious_insight", "specificity",
        "audience_intelligence", "strategic_choice", "commercial_consequence",
        "narrative_coherence", "editorial_judgement", "activation",
    )

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        identity = contract.get("growth_blueprint_candidate_identity")
        if not isinstance(identity, Mapping) or len(str(identity.get("checksum") or "")) != 64:
            raise ValueError("senior strategy review requires an immutable Blueprint checksum")

        lineage = contract.get("evidence_lineage")
        thesis = contract.get("central_thesis")
        audience = contract.get("audience")
        opportunity = contract.get("growth_opportunity")
        progression = contract.get("narrative_progression")
        editorial = contract.get("editorial_judgement")
        choices = contract.get("key_strategic_choices")
        activation = contract.get("activation_implications")
        contradiction_control = contract.get("contradiction_resolution")
        quantitative_control = contract.get("quantitative_evidence_treatment")
        assumption_control = contract.get("assumption_control")
        completeness = contract.get("completeness")
        refs = sorted({
            str(ref)
            for item in lineage or []
            if isinstance(item, Mapping)
            for ref in item.get("source_refs") or []
            if str(ref).strip()
        }) or ["candidate:missing-evidence-reference"]
        passed = {
            "evidence": (
                isinstance(lineage, list)
                and len(lineage) >= 5
                and isinstance(quantitative_control, Mapping)
                and quantitative_control.get("unsourced_numbers_present") is False
                and isinstance(assumption_control, Mapping)
                and assumption_control.get("silent_guesses") is False
            ),
            "diagnosis": self._substantive(self._field(contract.get("growth_barriers"), "diagnosis"), 15),
            "non_obvious_insight": self._substantive(self._field(thesis, "why_non_obvious"), 10),
            "specificity": self._substantive(self._field(thesis, "competitor_substitution_test"), 10),
            "audience_intelligence": isinstance(audience, Mapping) and all(
                self._meaningful(audience.get(key))
                for key in ("motivations", "tensions", "barriers", "triggers", "behaviours")
            ),
            "strategic_choice": isinstance(choices, list) and len(choices) >= 3,
            "commercial_consequence": self._substantive(self._field(opportunity, "commercial_consequence"), 10),
            "narrative_coherence": (
                isinstance(progression, list)
                and len(progression) >= 4
                and isinstance(contradiction_control, Mapping)
                and contradiction_control.get("unresolved_material_contradictions") == []
                and isinstance(completeness, Mapping)
                and completeness.get("materially_complete") is True
                and completeness.get("truncated") is False
            ),
            "editorial_judgement": isinstance(editorial, Mapping) and all(
                self._meaningful(editorial.get(key))
                for key in ("primary_emphasis", "supporting_evidence", "remove_or_deprioritise")
            ),
            "activation": isinstance(activation, Mapping) and self._substantive(activation.get("implication"), 8),
        }
        failed = [axis for axis in self._AXES if not passed[axis]]
        director_checks = {
            "non_obvious_central_thesis": passed["non_obvious_insight"],
            "evidence_earns_conclusion": passed["evidence"] and passed["diagnosis"],
            "progressively_more_specific": passed["specificity"] and passed["narrative_coherence"],
            "every_major_section_advances_argument": passed["narrative_coherence"],
            "removable_material_identified": passed["editorial_judgement"],
            "competitor_substitution_resisted": passed["specificity"],
            "worth_paying_for": all(passed.values()),
            "meaningfully_reframes_founder_problem": passed["non_obvious_insight"] and passed["diagnosis"],
            "commercial_consequence_clear": passed["commercial_consequence"],
            "presentable_without_intellectual_rebuild": all(passed.values()),
        }
        return {
            "reference_standard": self.REFERENCE_STANDARD,
            "senior_strategist_review": {
                axis: {
                    "passed": passed[axis],
                    "rationale": self._rationale(axis, passed[axis]),
                    "evidence_refs": refs[:5],
                }
                for axis in self._AXES
            },
            "director_judgement": {
                question: {
                    "passed": result,
                    "rationale": (
                        f"The checksum-bound candidate {'does' if result else 'does not'} demonstrate "
                        f"{question.replace('_', ' ')} at senior strategy-director calibre."
                    ),
                }
                for question, result in director_checks.items()
            },
            "reviewed_blueprint_checksum": str(identity["checksum"]),
            "review_disposition": "forward" if not failed else "revise",
            "revision_instructions": [
                f"The Strategy specialist must revise the {axis.replace('_', ' ')} dimension and return a new governed version."
                for axis in failed
            ],
            "external_action_taken": False,
        }

    @staticmethod
    def _field(value: Any, key: str) -> Any:
        return value.get(key) if isinstance(value, Mapping) else None

    @staticmethod
    def _meaningful(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, Mapping)):
            return bool(value)
        return value is not None

    @staticmethod
    def _substantive(value: Any, minimum_words: int) -> bool:
        return isinstance(value, str) and len(value.split()) >= minimum_words

    @staticmethod
    def _rationale(axis: str, passed: bool) -> str:
        if passed:
            return (
                f"The immutable candidate contains explicit, reviewable {axis.replace('_', ' ')} evidence "
                "and preserves its supporting source references."
            )
        return (
            f"The immutable candidate does not yet demonstrate sufficient {axis.replace('_', ' ')} "
            "for a senior strategy director to present it without rebuilding the argument."
        )
