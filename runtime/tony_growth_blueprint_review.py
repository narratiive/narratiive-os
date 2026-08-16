from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class GrowthBlueprintReview:
    status: str
    checks: dict[str, bool]
    failed_checks: tuple[str, ...]
    recommendation: str
    evidence_basis: str = "verified_claude_growth_blueprint"

    @property
    def ready_for_approval(self) -> bool:
        return self.status == "ready_for_approval"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": dict(self.checks),
            "failed_checks": list(self.failed_checks),
            "recommendation": self.recommendation,
            "evidence_basis": self.evidence_basis,
            "judgement_owner": "Tony",
        }


class TonyGrowthBlueprintReviewer:
    """Conservative quality gate for Claude-prepared inbound Growth Blueprints.

    Claude may prepare the work autonomously, but Tony owns the decision to advance it.
    The gate requires a concrete Blueprint, source-backed evidence, explicit evidence gaps,
    Narratiive fit, a strategic opportunity, and an explicit advance/revise/stop decision.
    It never performs an external write.
    """

    _BLUEPRINT_KEYS = ("growth_blueprint", "blueprint", "work_product", "artifact")
    _SOURCE_KEYS = ("sources", "source_backed_evidence", "evidence_sources", "citations")
    _GAP_KEYS = ("evidence_gaps", "gaps", "assumptions")
    _FIT_KEYS = ("narratiive_fit", "fit", "fit_assessment")
    _OPPORTUNITY_KEYS = ("strategic_growth_opportunity", "growth_opportunity", "opportunity")
    _DECISION_KEYS = ("recommendation", "decision", "disposition")

    def review(self, evidence: Mapping[str, Any]) -> GrowthBlueprintReview:
        blueprint = self._first(evidence, self._BLUEPRINT_KEYS)
        sources = self._first(evidence, self._SOURCE_KEYS)
        gaps = self._first(evidence, self._GAP_KEYS)
        fit = self._first(evidence, self._FIT_KEYS)
        opportunity = self._first(evidence, self._OPPORTUNITY_KEYS)
        decision = self._first(evidence, self._DECISION_KEYS).casefold()

        checks = {
            "blueprint_present": len(blueprint.split()) >= 40,
            "source_backed_evidence_present": bool(sources),
            "evidence_gaps_explicit": bool(gaps),
            "narratiive_fit_explicit": bool(fit),
            "strategic_opportunity_explicit": bool(opportunity),
            "advance_revise_stop_explicit": any(word in decision for word in ("advance", "revise", "stop")),
        }
        failed = tuple(name for name, passed in checks.items() if not passed)
        if failed:
            return GrowthBlueprintReview(
                status="revision_required",
                checks=checks,
                failed_checks=failed,
                recommendation="Return the Growth Blueprint to Claude for revision against the failed quality checks. Do not prepare outreach yet.",
            )

        if "stop" in decision:
            return GrowthBlueprintReview(
                status="stop_recommended",
                checks=checks,
                failed_checks=(),
                recommendation="Do not progress this opportunity to outreach; retain the evidence and rationale for commercial learning.",
            )
        if "revise" in decision:
            return GrowthBlueprintReview(
                status="revision_required",
                checks=checks,
                failed_checks=(),
                recommendation="Return the Growth Blueprint to Claude for the stated revision before any outreach preparation.",
            )
        return GrowthBlueprintReview(
            status="ready_for_approval",
            checks=checks,
            failed_checks=(),
            recommendation="Present the evidence-grounded Growth Blueprint to Matt for the commercial approval gate before outreach preparation.",
        )

    @staticmethod
    def _render(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, Mapping):
            return " ".join(f"{key}: {TonyGrowthBlueprintReviewer._render(item)}" for key, item in value.items()).strip()
        if isinstance(value, (list, tuple, set)):
            return " ".join(TonyGrowthBlueprintReviewer._render(item) for item in value).strip()
        return str(value).strip()

    @classmethod
    def _first(cls, evidence: Mapping[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            rendered = cls._render(evidence.get(key))
            if rendered:
                return rendered
        return ""
