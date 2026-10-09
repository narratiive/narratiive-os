from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SeniorStrategistReviewWorker:
    """Independent, read-only review using Rave calibre, never Rave content."""

    REFERENCE_STANDARD = "Rave Coffee Growth Blueprint calibre, not content template"

    _AXES = (
        "strategic_coherence", "non_obviousness", "client_specificity",
        "evidence_support", "audience_insight", "commercial_consequence",
        "narrative_progression", "editorial_judgement", "activation_usefulness",
    )

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        identity = contract.get("blueprint_director_output_identity")
        if not isinstance(identity, Mapping) or len(str(identity.get("checksum") or "")) != 64:
            raise ValueError("senior strategy review requires an immutable Blueprint Director checksum")

        lineage = contract.get("evidence_lineage")
        thesis = contract.get("central_thesis")
        audience = contract.get("audience")
        opportunity = contract.get("growth_opportunity")
        progression = contract.get("narrative_progression")
        editorial = contract.get("editorial_judgement")
        activation = contract.get("activation_implications")
        quantitative_control = contract.get("quantitative_evidence_treatment")
        assumption_control = contract.get("assumption_control")
        completeness = contract.get("completeness")
        blueprint = contract.get("client_facing_blueprint")
        pages = blueprint.get("pages") if isinstance(blueprint, Mapping) else None
        trace = contract.get("editorial_trace")
        client_context = contract.get("client_context")
        client_name = ""
        if isinstance(client_context, Mapping):
            client_name = str(
                client_context.get("brand_name")
                or client_context.get("company_name")
                or client_context.get("company")
                or client_context.get("name")
                or ""
            ).strip()
        visible = " ".join(
            str(value)
            for page in pages or []
            if isinstance(page, Mapping)
            for value in (page.get("headline"), page.get("body"), page.get("commercial_consequence"))
        )
        refs = sorted({
            str(ref)
            for item in lineage or []
            if isinstance(item, Mapping)
            for ref in item.get("source_refs") or []
            if str(ref).strip()
        }) or ["candidate:missing-evidence-reference"]
        traced_refs = {
            str(ref)
            for item in trace or []
            if isinstance(item, Mapping)
            for ref in item.get("evidence_refs") or []
            if str(ref).strip()
        }
        page_numbers = [
            page.get("page_number")
            for page in pages or []
            if isinstance(page, Mapping)
        ]
        passed = {
            "strategic_coherence": (
                isinstance(blueprint, Mapping)
                and self._substantive(blueprint.get("central_argument"), 12)
                and isinstance(pages, list)
                and bool(pages)
            ),
            "non_obviousness": self._substantive(self._field(thesis, "why_non_obvious"), 10),
            "client_specificity": bool(client_name) and client_name.casefold() in visible.casefold(),
            "evidence_support": (
                isinstance(lineage, list)
                and len(lineage) >= 5
                and isinstance(trace, list)
                and isinstance(pages, list)
                and len(trace) == len(pages)
                and all(
                    isinstance(item, Mapping)
                    and item.get("page_number") == page_number
                    and item.get("evidence_refs")
                    for page_number, item in zip(page_numbers, trace)
                )
                and bool(traced_refs)
                and traced_refs
                and isinstance(quantitative_control, Mapping)
                and quantitative_control.get("unsourced_numbers_present") is False
                and isinstance(assumption_control, Mapping)
                and assumption_control.get("silent_guesses") is False
            ),
            "audience_insight": isinstance(audience, Mapping) and all(
                self._meaningful(audience.get(key))
                for key in ("motivations", "tensions", "barriers", "triggers", "behaviours")
            ),
            "commercial_consequence": self._substantive(self._field(opportunity, "commercial_consequence"), 10),
            "narrative_progression": (
                isinstance(progression, list)
                and len(progression) >= 4
                and isinstance(completeness, Mapping)
                and completeness.get("materially_complete") is True
                and completeness.get("truncated") is False
                and isinstance(pages, list)
                and bool(pages)
                and page_numbers == list(range(1, len(pages) + 1))
            ),
            "editorial_judgement": isinstance(editorial, Mapping) and all(
                self._meaningful(editorial.get(key))
                for key in ("primary_emphasis", "supporting_evidence", "remove_or_deprioritise")
            ),
            "activation_usefulness": isinstance(activation, Mapping) and self._substantive(activation.get("implication"), 8),
        }
        failed = [axis for axis in self._AXES if not passed[axis]]
        actionable_findings = [
            self._actionable_finding(axis, pages, trace, passed)
            for axis in failed
        ]
        director_checks = {
            "non_obvious_central_thesis": passed["non_obviousness"],
            "evidence_earns_conclusion": passed["evidence_support"] and passed["strategic_coherence"],
            "progressively_more_specific": passed["client_specificity"] and passed["narrative_progression"],
            "every_major_section_advances_argument": passed["narrative_progression"],
            "removable_material_identified": passed["editorial_judgement"],
            "competitor_substitution_resisted": passed["client_specificity"],
            "worth_paying_for": all(passed.values()),
            "meaningfully_reframes_founder_problem": passed["non_obviousness"] and passed["strategic_coherence"],
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
            "actionable_findings": actionable_findings,
            "revision_instructions": [finding["corrective_action"] for finding in actionable_findings],
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

    @classmethod
    def _actionable_finding(cls, axis: str, pages: Any, trace: Any, passed: Mapping[str, bool]) -> dict[str, Any]:
        page_numbers = [
            page.get("page_number") for page in pages or []
            if isinstance(page, Mapping) and page.get("page_number") is not None
        ]
        if axis == "evidence_support":
            affected = page_numbers or ["all"]
            gap = "material claims are not sufficiently tied to supplied evidence or labelled as inference/hypothesis"
            action = "Annotate each affected claim with its evidence basis or qualification, then remove or reframe unsupported commercial outcomes."
        elif axis == "narrative_progression":
            affected = page_numbers or ["all"]
            gap = "the sequence does not yet show a cumulative move from diagnosis to choice to consequence"
            action = "Compress repeated diagnosis, assign each section a distinct decision, and reorder pages so every step makes the next recommendation more consequential."
        else:
            affected = page_numbers or ["all"]
            gap = f"the {axis.replace('_', ' ')} test is not met"
            action = f"Revise the affected pages ({', '.join(map(str, affected))}) to close this gap against the governed evidence and return a new version."
        return {"axis": axis, "affected_pages": affected, "gap": gap, "corrective_action": action}
