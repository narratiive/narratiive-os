from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


VALID_DOMAIN_STATES = {"connected", "not_connected", "degraded"}
REQUIRED_MISSION_CONTROL_DOMAINS = (
    "health",
    "active_work",
    "approvals",
    "commercial_pipeline",
    "publishing",
    "risks",
    "opportunities",
    "recommended_focus",
    "recent_wins",
)


@dataclass(frozen=True, slots=True)
class MissionControlDomainStatus:
    """Availability and evidence for one canonical Mission Control domain."""

    domain: str
    state: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        domain = self.domain.strip().lower()
        if domain not in REQUIRED_MISSION_CONTROL_DOMAINS:
            raise ValueError(f"Unsupported Mission Control domain: {self.domain}")
        if self.state not in VALID_DOMAIN_STATES:
            raise ValueError(f"Unsupported Mission Control domain state: {self.state}")
        evidence = tuple(dict.fromkeys(item.strip() for item in self.evidence if item.strip()))
        if self.state in {"connected", "degraded"} and not evidence:
            raise ValueError(f"{self.state} Mission Control domains require evidence")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "evidence", evidence)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        return payload


class MissionControlDomainRegistry:
    """Resolve every required executive domain without fabricating integrations.

    Callers provide only canonical adapter results. Any required domain without
    a result is returned explicitly as ``not_connected`` so presentation layers
    never infer availability from absence.
    """

    def resolve(
        self,
        values: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> tuple[MissionControlDomainStatus, ...]:
        supplied = values or {}
        unknown = sorted(set(supplied) - set(REQUIRED_MISSION_CONTROL_DOMAINS))
        if unknown:
            raise ValueError(f"Unsupported Mission Control domains: {', '.join(unknown)}")

        statuses: list[MissionControlDomainStatus] = []
        for domain in REQUIRED_MISSION_CONTROL_DOMAINS:
            payload = supplied.get(domain)
            if payload is None:
                statuses.append(
                    MissionControlDomainStatus(
                        domain=domain,
                        state="not_connected",
                    )
                )
                continue

            state = str(payload.get("state", "")).strip().lower()
            evidence_value = payload.get("evidence", ())
            if isinstance(evidence_value, str):
                evidence = (evidence_value,)
            elif isinstance(evidence_value, (list, tuple)):
                evidence = tuple(str(item) for item in evidence_value)
            else:
                raise ValueError(f"Invalid evidence for Mission Control domain: {domain}")
            statuses.append(
                MissionControlDomainStatus(
                    domain=domain,
                    state=state,
                    evidence=evidence,
                )
            )
        return tuple(statuses)

    def to_dict(
        self,
        values: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        return {item.domain: item.to_dict() for item in self.resolve(values)}
