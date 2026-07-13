from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .artifact_catalog import ArtifactRecord


class ScoreRecommendation(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class EvidenceSignal:
    evidence_id: str
    supported: bool
    source_quality: int
    source_artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        if not 0 <= self.source_quality <= 100:
            raise ValueError("source_quality must be between 0 and 100")
        if self.supported and not self.source_artifact_ids:
            raise ValueError("supported evidence must reference a source artifact")
        object.__setattr__(
            self,
            "source_artifact_ids",
            tuple(self.source_artifact_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "supported": self.supported,
            "source_quality": self.source_quality,
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceSignal":
        supported = data["supported"]
        if not isinstance(supported, bool):
            raise ValueError("supported must be a boolean")
        return cls(
            evidence_id=str(data["evidence_id"]),
            supported=supported,
            source_quality=int(data["source_quality"]),
            source_artifact_ids=tuple(
                str(item) for item in data.get("source_artifact_ids") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class ArtifactSignal:
    artifact_id: str
    stage_id: str
    parent_artifact_ids: tuple[str, ...] = ()
    expected_parent_artifact_ids: tuple[str, ...] = ()
    open_inputs: tuple[str, ...] = ()
    strategic_checks: Mapping[str, bool] = field(default_factory=dict)
    creative_checks: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id.strip() or not self.stage_id.strip():
            raise ValueError("artifact_id and stage_id must not be empty")
        object.__setattr__(
            self,
            "parent_artifact_ids",
            tuple(self.parent_artifact_ids),
        )
        object.__setattr__(
            self,
            "expected_parent_artifact_ids",
            tuple(self.expected_parent_artifact_ids),
        )
        object.__setattr__(self, "open_inputs", tuple(self.open_inputs))
        object.__setattr__(
            self,
            "strategic_checks",
            dict(sorted(self.strategic_checks.items())),
        )
        object.__setattr__(
            self,
            "creative_checks",
            dict(sorted(self.creative_checks.items())),
        )

    @classmethod
    def from_record(
        cls,
        record: ArtifactRecord,
        *,
        expected_parent_artifact_ids: Iterable[str] = (),
        open_inputs: Iterable[str] = (),
        strategic_checks: Mapping[str, bool] | None = None,
        creative_checks: Mapping[str, bool] | None = None,
    ) -> "ArtifactSignal":
        return cls(
            artifact_id=record.artifact.artifact_id,
            stage_id=record.stage_id,
            parent_artifact_ids=record.parent_artifact_ids,
            expected_parent_artifact_ids=tuple(expected_parent_artifact_ids),
            open_inputs=tuple(open_inputs),
            strategic_checks=dict(strategic_checks or {}),
            creative_checks=dict(creative_checks or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "stage_id": self.stage_id,
            "parent_artifact_ids": list(self.parent_artifact_ids),
            "expected_parent_artifact_ids": list(
                self.expected_parent_artifact_ids
            ),
            "open_inputs": list(self.open_inputs),
            "strategic_checks": dict(self.strategic_checks),
            "creative_checks": dict(self.creative_checks),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactSignal":
        return cls(
            artifact_id=str(data["artifact_id"]),
            stage_id=str(data["stage_id"]),
            parent_artifact_ids=tuple(
                str(item) for item in data.get("parent_artifact_ids") or ()
            ),
            expected_parent_artifact_ids=tuple(
                str(item)
                for item in data.get("expected_parent_artifact_ids") or ()
            ),
            open_inputs=tuple(
                str(item) for item in data.get("open_inputs") or ()
            ),
            strategic_checks=_boolean_checks(
                data.get("strategic_checks"),
                "strategic_checks",
            ),
            creative_checks=_boolean_checks(
                data.get("creative_checks"),
                "creative_checks",
            ),
        )


@dataclass(frozen=True, slots=True)
class ScoringInput:
    artifacts: tuple[ArtifactSignal, ...]
    evidence: tuple[EvidenceSignal, ...]
    unsupported_claims: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.artifacts:
            raise ValueError("scoring input must include at least one artifact")
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(
            self,
            "unsupported_claims",
            tuple(self.unsupported_claims),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": [item.to_dict() for item in self.artifacts],
            "evidence": [item.to_dict() for item in self.evidence],
            "unsupported_claims": list(self.unsupported_claims),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoringInput":
        return cls(
            artifacts=tuple(
                ArtifactSignal.from_dict(item)
                for item in data.get("artifacts") or ()
            ),
            evidence=tuple(
                EvidenceSignal.from_dict(item)
                for item in data.get("evidence") or ()
            ),
            unsupported_claims=tuple(
                str(item) for item in data.get("unsupported_claims") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class DimensionScore:
    value: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError("score must be between 0 and 100")
        if not self.reasons:
            raise ValueError("score reasons must not be empty")
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "reasons": list(self.reasons)}


@dataclass(frozen=True, slots=True)
class ConfidenceScorecard:
    scorecard_id: str
    input_checksum: str
    evidence_coverage: DimensionScore
    source_quality: DimensionScore
    strategic_confidence: DimensionScore
    creative_confidence: DimensionScore
    overall_risk: DimensionScore
    recommendation: ScoreRecommendation
    policy_reasons: tuple[str, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scorecard_id": self.scorecard_id,
            "input_checksum": self.input_checksum,
            "evidence_coverage": self.evidence_coverage.to_dict(),
            "source_quality": self.source_quality.to_dict(),
            "strategic_confidence": self.strategic_confidence.to_dict(),
            "creative_confidence": self.creative_confidence.to_dict(),
            "overall_risk": self.overall_risk.to_dict(),
            "recommendation": self.recommendation.value,
            "policy_reasons": list(self.policy_reasons),
        }


class ConfidenceEngine:
    """Produces deterministic, auditable confidence scorecards."""

    def score(self, scoring_input: ScoringInput) -> ConfidenceScorecard:
        checksum = _input_checksum(scoring_input)
        coverage = self._evidence_coverage(scoring_input.evidence)
        source_quality = self._source_quality(scoring_input.evidence)
        strategic = self._checks(
            "strategic",
            (
                check
                for artifact in scoring_input.artifacts
                for check in artifact.strategic_checks.items()
            ),
        )
        creative = self._checks(
            "creative",
            (
                check
                for artifact in scoring_input.artifacts
                for check in artifact.creative_checks.items()
            ),
        )
        lineage_value, lineage_reasons = self._lineage(scoring_input.artifacts)
        open_inputs = tuple(
            f"{artifact.stage_id}:{marker}"
            for artifact in scoring_input.artifacts
            for marker in artifact.open_inputs
        )
        risk = self._risk(
            coverage=coverage.value,
            source_quality=source_quality.value,
            strategic=strategic.value,
            creative=creative.value,
            lineage=lineage_value,
            open_input_count=len(open_inputs),
            unsupported_claims=scoring_input.unsupported_claims,
            lineage_reasons=lineage_reasons,
        )
        recommendation, policy_reasons = self._recommend(
            coverage=coverage.value,
            source_quality=source_quality.value,
            strategic=strategic.value,
            creative=creative.value,
            lineage=lineage_value,
            risk=risk.value,
            open_inputs=open_inputs,
            unsupported_claims=scoring_input.unsupported_claims,
        )
        return ConfidenceScorecard(
            scorecard_id=f"score-{checksum[:16]}",
            input_checksum=checksum,
            evidence_coverage=coverage,
            source_quality=source_quality,
            strategic_confidence=strategic,
            creative_confidence=creative,
            overall_risk=risk,
            recommendation=recommendation,
            policy_reasons=policy_reasons,
        )

    @staticmethod
    def _evidence_coverage(
        evidence: tuple[EvidenceSignal, ...],
    ) -> DimensionScore:
        supported = sum(item.supported for item in evidence)
        value = round(100 * supported / len(evidence)) if evidence else 0
        return DimensionScore(
            value,
            (
                f"{supported} of {len(evidence)} evidence items are supported.",
            ),
        )

    @staticmethod
    def _source_quality(
        evidence: tuple[EvidenceSignal, ...],
    ) -> DimensionScore:
        supported = [item for item in evidence if item.supported]
        value = (
            round(sum(item.source_quality for item in supported) / len(supported))
            if supported
            else 0
        )
        return DimensionScore(
            value,
            (
                f"Average quality across {len(supported)} supported sources is {value}.",
            ),
        )

    @staticmethod
    def _checks(
        label: str,
        checks: Iterable[tuple[str, bool]],
    ) -> DimensionScore:
        ordered = tuple(checks)
        passed = sum(value for _, value in ordered)
        value = round(100 * passed / len(ordered)) if ordered else 0
        missing = sorted(name for name, result in ordered if not result)
        reasons = [f"{passed} of {len(ordered)} {label} checks passed."]
        if missing:
            reasons.append(f"Unmet {label} checks: {', '.join(missing)}.")
        return DimensionScore(value, tuple(reasons))

    @staticmethod
    def _lineage(
        artifacts: tuple[ArtifactSignal, ...],
    ) -> tuple[int, tuple[str, ...]]:
        expected = 0
        present = 0
        missing: list[str] = []
        for artifact in artifacts:
            parents = set(artifact.parent_artifact_ids)
            for parent_id in artifact.expected_parent_artifact_ids:
                expected += 1
                if parent_id in parents:
                    present += 1
                else:
                    missing.append(f"{artifact.artifact_id}->{parent_id}")
        value = round(100 * present / expected) if expected else 100
        reasons = [f"{present} of {expected} expected lineage links are present."]
        if missing:
            reasons.append(f"Missing lineage links: {', '.join(sorted(missing))}.")
        return value, tuple(reasons)

    @staticmethod
    def _risk(
        *,
        coverage: int,
        source_quality: int,
        strategic: int,
        creative: int,
        lineage: int,
        open_input_count: int,
        unsupported_claims: tuple[str, ...],
        lineage_reasons: tuple[str, ...],
    ) -> DimensionScore:
        open_input_risk = min(100, open_input_count * 25)
        value = round(
            (100 - coverage) * 0.25
            + (100 - source_quality) * 0.15
            + (100 - strategic) * 0.20
            + (100 - creative) * 0.20
            + (100 - lineage) * 0.15
            + open_input_risk * 0.05
        )
        if unsupported_claims:
            value = max(value, 85)
        reasons = [
            (
                "Weighted risk uses evidence coverage, source quality, strategic "
                "confidence, creative confidence, lineage and open inputs."
            ),
            *lineage_reasons,
            f"{open_input_count} open-input markers contribute to risk.",
        ]
        if unsupported_claims:
            reasons.append(
                f"{len(unsupported_claims)} unsupported claims set the risk floor to 85."
            )
        return DimensionScore(min(100, value), tuple(reasons))

    @staticmethod
    def _recommend(
        *,
        coverage: int,
        source_quality: int,
        strategic: int,
        creative: int,
        lineage: int,
        risk: int,
        open_inputs: tuple[str, ...],
        unsupported_claims: tuple[str, ...],
    ) -> tuple[ScoreRecommendation, tuple[str, ...]]:
        if unsupported_claims:
            return (
                ScoreRecommendation.BLOCK,
                (
                    "Unsupported claims require a BLOCK recommendation: "
                    + ", ".join(unsupported_claims),
                ),
            )
        if coverage < 40 or risk >= 70:
            return (
                ScoreRecommendation.BLOCK,
                (
                    f"Blocking threshold met: evidence={coverage}, risk={risk}.",
                ),
            )
        revision_reasons: list[str] = []
        thresholds = {
            "evidence coverage": (coverage, 80),
            "source quality": (source_quality, 60),
            "strategic confidence": (strategic, 70),
            "creative confidence": (creative, 70),
            "lineage completeness": (lineage, 100),
        }
        for label, (value, threshold) in thresholds.items():
            if value < threshold:
                revision_reasons.append(
                    f"{label} {value} is below the {threshold} threshold."
                )
        if risk >= 35:
            revision_reasons.append(f"overall risk {risk} is at or above 35.")
        if open_inputs:
            revision_reasons.append(
                "Open inputs require resolution: " + ", ".join(open_inputs) + "."
            )
        if revision_reasons:
            return ScoreRecommendation.REVISE, tuple(revision_reasons)
        return (
            ScoreRecommendation.APPROVE,
            (
                "All approval thresholds passed; the reviewer may still apply "
                "stricter policy.",
            ),
        )


def _input_checksum(scoring_input: ScoringInput) -> str:
    payload = json.dumps(
        scoring_input.to_dict(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _boolean_checks(
    raw: Any,
    field_name: str,
) -> dict[str, bool]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"{field_name} must be an object")
    checks: dict[str, bool] = {}
    for key, value in raw.items():
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} values must be booleans")
        checks[str(key)] = value
    return checks
