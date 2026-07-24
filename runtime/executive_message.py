from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class ExecutiveUrgency(str, Enum):
    ROUTINE = "routine"
    TODAY = "today"
    IMMEDIATE = "immediate"


class ExecutiveConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A stable pointer to recorded evidence, never an inferred source."""

    reference: str
    label: str = ""

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("evidence reference is required")

    def to_dict(self) -> dict[str, str]:
        return {"reference": self.reference, "label": self.label}


@dataclass(frozen=True, slots=True)
class ExecutiveMessage:
    """Deterministic manager-facing interpretation of recorded system state."""

    observation: str
    implication: str
    recommendation: str
    human_effort: str
    confidence: ExecutiveConfidence
    evidence: tuple[EvidenceReference, ...]
    urgency: ExecutiveUrgency = ExecutiveUrgency.ROUTINE
    interruption_eligible: bool = False

    def __post_init__(self) -> None:
        for field_name in ("observation", "implication", "recommendation", "human_effort"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if not self.evidence:
            raise ValueError("at least one evidence reference is required")
        if self.interruption_eligible and self.urgency is ExecutiveUrgency.ROUTINE:
            raise ValueError("routine messages cannot interrupt")

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation,
            "implication": self.implication,
            "recommendation": self.recommendation,
            "human_effort": self.human_effort,
            "confidence": self.confidence.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "urgency": self.urgency.value,
            "interruption_eligible": self.interruption_eligible,
        }

    def render_compact(self) -> str:
        """Render business language suitable for Telegram without technical internals."""

        lines = [
            self.observation,
            f"Why it matters: {self.implication}",
            f"Recommendation: {self.recommendation}",
            f"Your effort: {self.human_effort}",
            f"Confidence: {self.confidence.value}",
        ]
        return "\n".join(lines)


def build_executive_message(
    *,
    observation: str,
    implication: str,
    recommendation: str,
    human_effort: str,
    evidence: Sequence[str | Mapping[str, str]],
    confidence: ExecutiveConfidence = ExecutiveConfidence.HIGH,
    urgency: ExecutiveUrgency = ExecutiveUrgency.ROUTINE,
    interruption_eligible: bool = False,
) -> ExecutiveMessage:
    """Build a normalized message from repository or gateway evidence references."""

    normalized: list[EvidenceReference] = []
    for item in evidence:
        if isinstance(item, str):
            normalized.append(EvidenceReference(reference=item))
        elif isinstance(item, Mapping):
            normalized.append(
                EvidenceReference(
                    reference=str(item.get("reference", "")),
                    label=str(item.get("label", "")),
                )
            )
        else:
            raise TypeError("evidence entries must be strings or mappings")
    return ExecutiveMessage(
        observation=observation,
        implication=implication,
        recommendation=recommendation,
        human_effort=human_effort,
        confidence=confidence,
        evidence=tuple(normalized),
        urgency=urgency,
        interruption_eligible=interruption_eligible,
    )
