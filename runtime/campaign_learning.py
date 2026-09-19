from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from runtime.campaign_engine import CampaignIdentity
from runtime.media_control import CanonicalMediaSnapshot, MediaAuthority, MediaRecommendation


class CampaignLearningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PerformanceEvidenceRecord:
    record_id: str
    identity: CampaignIdentity
    period_start: str
    period_end: str
    providers: tuple[str, ...]
    snapshot_checksums: tuple[str, ...]
    mapped_asset_version_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.record_id.strip() or not self.period_start.strip() or not self.period_end.strip():
            raise CampaignLearningError("performance evidence requires identity and period")
        if not self.providers or len(self.providers) != len(set(self.providers)):
            raise CampaignLearningError("performance evidence requires unique providers")
        if len(self.providers) != len(self.snapshot_checksums):
            raise CampaignLearningError("performance evidence requires one checksum per provider snapshot")
        if len(self.mapped_asset_version_ids) != len(set(self.mapped_asset_version_ids)):
            raise CampaignLearningError("performance evidence asset version IDs must be unique")


@dataclass(frozen=True, slots=True)
class CampaignInsightRecord:
    insight_id: str
    identity: CampaignIdentity
    source_performance_record_id: str
    source_recommendation_id: str
    severity: str
    category: str
    summary: str
    evidence: tuple[str, ...]
    proposed_action: str
    evidence_grade: str
    human_review_required: bool = True

    def __post_init__(self) -> None:
        required = (
            self.insight_id,
            self.source_performance_record_id,
            self.source_recommendation_id,
            self.severity,
            self.category,
            self.summary,
            self.proposed_action,
            self.evidence_grade,
        )
        if any(not value.strip() for value in required) or not self.evidence:
            raise CampaignLearningError("campaign insight requires recommendation and evidence lineage")
        if not self.human_review_required:
            raise CampaignLearningError("campaign insights must require human review")


@dataclass(frozen=True, slots=True)
class CreativeIterationProposal:
    proposal_id: str
    identity: CampaignIdentity
    source_performance_record_id: str
    source_insight_id: str
    source_asset_version_ids: tuple[str, ...]
    objective: str
    hypothesis: str
    requested_changes: tuple[str, ...]
    status: str = "pending_human_approval"
    production_authorised: bool = False
    publication_authorised: bool = False
    media_spend_authorised: bool = False

    def __post_init__(self) -> None:
        required = (
            self.proposal_id,
            self.source_performance_record_id,
            self.source_insight_id,
            self.objective,
            self.hypothesis,
        )
        if any(not value.strip() for value in required):
            raise CampaignLearningError("creative iteration proposal requires complete evidence lineage")
        if not self.source_asset_version_ids or len(self.source_asset_version_ids) != len(set(self.source_asset_version_ids)):
            raise CampaignLearningError("creative iteration proposal requires unique source asset versions")
        if not self.requested_changes:
            raise CampaignLearningError("creative iteration proposal requires bounded requested changes")
        if self.status != "pending_human_approval":
            raise CampaignLearningError("creative iteration proposal must begin pending human approval")
        if self.production_authorised or self.publication_authorised or self.media_spend_authorised:
            raise CampaignLearningError("creative iteration proposal cannot authorise production, publication or spend")


@dataclass(frozen=True, slots=True)
class CampaignLearningCycle:
    cycle_id: str
    performance: PerformanceEvidenceRecord
    insights: tuple[CampaignInsightRecord, ...]
    iteration_proposals: tuple[CreativeIterationProposal, ...]
    checksum: str
    notion_projection_required: bool = True
    external_action_taken: bool = False

    def __post_init__(self) -> None:
        if not self.cycle_id.strip() or not self.checksum.strip() or not self.insights:
            raise CampaignLearningError("campaign learning cycle requires performance and insights")
        if not self.notion_projection_required or self.external_action_taken:
            raise CampaignLearningError("learning cycles are internal evidence pending Notion projection")
        if any(item.identity != self.performance.identity for item in self.insights):
            raise CampaignLearningError("insight identity must match performance identity")
        if any(item.identity != self.performance.identity for item in self.iteration_proposals):
            raise CampaignLearningError("iteration identity must match performance identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "performance": _as_record(self.performance),
            "insights": [_as_record(item) for item in self.insights],
            "iteration_proposals": [_as_record(item) for item in self.iteration_proposals],
            "checksum": self.checksum,
            "notion_projection_required": self.notion_projection_required,
            "external_action_taken": self.external_action_taken,
        }


class CampaignLearningService:
    """Convert normalized read-only media evidence into bounded learning records."""

    def build(
        self,
        snapshots: Sequence[CanonicalMediaSnapshot],
        recommendations: Sequence[MediaRecommendation],
        *,
        approved_asset_version_ids: Iterable[str],
    ) -> CampaignLearningCycle:
        if not snapshots:
            raise CampaignLearningError("campaign learning requires normalized performance snapshots")
        identity = snapshots[0].identity
        if any(item.identity != identity for item in snapshots):
            raise CampaignLearningError("campaign learning snapshots must share one canonical identity")
        providers = tuple(sorted(item.provider.value for item in snapshots))
        if len(providers) != len(set(providers)):
            raise CampaignLearningError("campaign learning accepts one latest snapshot per provider")
        periods = {(item.period_start, item.period_end) for item in snapshots}
        if len(periods) != 1:
            raise CampaignLearningError("campaign learning snapshots must share one reporting period")
        period_start, period_end = next(iter(periods))
        approved_ids = {str(item).strip() for item in approved_asset_version_ids if str(item).strip()}
        if not approved_ids:
            raise CampaignLearningError("campaign learning requires the exact approved asset version IDs")
        mapped_ids = {
            mapping.narratiive_asset_id
            for snapshot in snapshots
            for mapping in snapshot.creative_mappings
        }
        if not mapped_ids.issubset(approved_ids):
            raise CampaignLearningError("provider creative mapping references an unapproved Narratiive asset version")
        snapshot_checksums = tuple(_checksum(item.to_dict()) for item in sorted(snapshots, key=lambda value: value.provider.value))
        performance_payload = {
            "identity": asdict(identity),
            "period_start": period_start,
            "period_end": period_end,
            "providers": providers,
            "snapshot_checksums": snapshot_checksums,
            "mapped_asset_version_ids": sorted(mapped_ids),
        }
        performance_hash = _checksum(performance_payload)
        performance = PerformanceEvidenceRecord(
            record_id=f"performance-{identity.campaign_id}-{performance_hash[:16]}",
            identity=identity,
            period_start=period_start,
            period_end=period_end,
            providers=providers,
            snapshot_checksums=snapshot_checksums,
            mapped_asset_version_ids=tuple(sorted(mapped_ids)),
        )
        insights = []
        recommendation_ids = [item.recommendation_id for item in recommendations]
        if len(recommendation_ids) != len(set(recommendation_ids)):
            raise CampaignLearningError("campaign learning recommendation IDs must be unique")
        for recommendation in recommendations:
            if recommendation.client_id != identity.client_id or recommendation.campaign_id != identity.campaign_id:
                raise CampaignLearningError("recommendation identity does not match performance evidence")
            if recommendation.authority is not MediaAuthority.RECOMMEND or not recommendation.human_approval_required:
                raise CampaignLearningError("campaign learning accepts advisory recommendations only")
            if not recommendation.evidence:
                raise CampaignLearningError("campaign learning recommendations require evidence")
            evidence_grade = "provider_observation"
            insight_hash = _checksum({"performance": performance.record_id, **recommendation.to_dict()})
            insights.append(
                CampaignInsightRecord(
                    insight_id=f"insight-{identity.campaign_id}-{insight_hash[:16]}",
                    identity=identity,
                    source_performance_record_id=performance.record_id,
                    source_recommendation_id=recommendation.recommendation_id,
                    severity=recommendation.severity,
                    category=recommendation.category,
                    summary=recommendation.summary,
                    evidence=tuple(recommendation.evidence),
                    proposed_action=recommendation.proposed_action,
                    evidence_grade=evidence_grade,
                )
            )
        if not insights:
            raise CampaignLearningError("campaign learning requires at least one evidence-backed recommendation")

        proposals = []
        if mapped_ids:
            for insight in insights:
                if insight.category not in {"poor_performer", "creative_rejected", "high_performer"}:
                    continue
                proposal_hash = _checksum({
                    "insight_id": insight.insight_id,
                    "asset_version_ids": sorted(mapped_ids),
                    "proposed_action": insight.proposed_action,
                })
                proposals.append(
                    CreativeIterationProposal(
                        proposal_id=f"iteration-{identity.campaign_id}-{proposal_hash[:16]}",
                        identity=identity,
                        source_performance_record_id=performance.record_id,
                        source_insight_id=insight.insight_id,
                        source_asset_version_ids=tuple(sorted(mapped_ids)),
                        objective=f"Respond to verified {insight.category.replace('_', ' ')} evidence without changing approved strategy.",
                        hypothesis=(
                            "A bounded creative variation based on the observed evidence may improve the next measured result; "
                            "this remains a hypothesis until Matt approves and a subsequent test is measured."
                        ),
                        requested_changes=(
                            insight.proposed_action,
                            "Preserve the approved Creative Bible and create a new append-only asset version.",
                            "Return the exact iteration brief and generated version for human approval before use.",
                        ),
                    )
                )
        cycle_payload = {
            "performance": _as_record(performance),
            "insights": [_as_record(item) for item in insights],
            "iteration_proposals": [_as_record(item) for item in proposals],
        }
        cycle_checksum = _checksum(cycle_payload)
        return CampaignLearningCycle(
            cycle_id=f"learning-{identity.campaign_id}-{cycle_checksum[:16]}",
            performance=performance,
            insights=tuple(insights),
            iteration_proposals=tuple(proposals),
            checksum=cycle_checksum,
        )


class FileCampaignLearningStore:
    """Append-only local evidence store; Notion projection remains explicitly required."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def persist(self, cycle: CampaignLearningCycle) -> Path:
        target = self.root / _safe(cycle.performance.identity.workspace_id) / _safe(cycle.performance.identity.client_id) / f"{_safe(cycle.cycle_id)}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(cycle.to_dict(), indent=2, sort_keys=True) + "\n"
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing.get("checksum") != cycle.checksum:
                raise CampaignLearningError("learning cycle ID is already bound to different evidence")
            return target
        temporary = target.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)
        return target


def _as_record(value: Any) -> dict[str, Any]:
    result = asdict(value)
    identity = result.get("identity")
    if isinstance(identity, Mapping):
        result["identity"] = dict(identity)
    return result


def _checksum(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value)[:120]
