from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from runtime.progress_engine import CampaignProgress, ProgressSnapshot, RepositoryProgressEngine


_STAGE_WORKERS = {
    "growth_specification": "tony",
    "growth_blueprint": "claude",
    "campaign_world": "claude",
    "creative_directors_bible": "claude",
    "production_pack": "codex",
    "asset_manifest": "production",
    "performance_feedback": "tony",
}


@dataclass(frozen=True)
class DispatchDecision:
    client_id: str
    client_name: str
    campaign_id: str
    campaign_name: str
    stage: str
    action: str
    assigned_worker: str | None
    status: str
    reason: str
    blocker_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TonyDispatcher:
    """Convert canonical repository state into one deterministic work decision."""

    def __init__(self, progress_engine: RepositoryProgressEngine) -> None:
        self.progress_engine = progress_engine

    def dispatch(self, objects: Iterable[dict[str, Any]]) -> DispatchDecision | None:
        return self.select(self.progress_engine.build_snapshot(objects))

    def select(self, snapshot: ProgressSnapshot) -> DispatchDecision | None:
        if not snapshot.campaigns:
            return None

        campaign = sorted(snapshot.campaigns, key=self._priority_key)[0]
        return self._decision(campaign)

    @staticmethod
    def _priority_key(campaign: CampaignProgress) -> tuple[Any, ...]:
        return (
            campaign.health != "blocked",
            campaign.completion_percent,
            campaign.client_name.casefold(),
            campaign.campaign_name.casefold(),
        )

    @staticmethod
    def _decision(campaign: CampaignProgress) -> DispatchDecision:
        if campaign.health == "blocked":
            blockers = ", ".join(campaign.blocker_codes) or "repository validation failed"
            return DispatchDecision(
                client_id=campaign.client_id,
                client_name=campaign.client_name,
                campaign_id=campaign.campaign_id,
                campaign_name=campaign.campaign_name,
                stage=campaign.current_stage,
                action=f"resolve repository blockers before {campaign.next_action}",
                assigned_worker=None,
                status="blocked",
                reason=f"Dispatch refused because canonical validation reported: {blockers}.",
                blocker_codes=campaign.blocker_codes,
            )

        if campaign.current_status == "in_review":
            worker = "matt"
            reason = "Human approval is required before the lifecycle can advance."
        elif campaign.next_action == "start the next Growth Specification cycle":
            worker = "tony"
            reason = "The canonical lifecycle is complete; Tony should initialise the next learning cycle."
        else:
            worker = _STAGE_WORKERS.get(campaign.current_stage, "tony")
            reason = f"{worker} owns the next executable action for {campaign.current_stage}."

        return DispatchDecision(
            client_id=campaign.client_id,
            client_name=campaign.client_name,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            stage=campaign.current_stage,
            action=campaign.next_action,
            assigned_worker=worker,
            status="ready",
            reason=reason,
            blocker_codes=(),
        )
