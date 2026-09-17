from __future__ import annotations

from runtime.campaign_engine import (
    CampaignEngine,
    CampaignEngineError,
    CampaignEngineStage,
    CampaignEngineState,
    ProductionJobRoute,
)
from runtime.worker_registry import CapabilityWorkerRegistry, WorkerSelectionPolicy


class CampaignProductionRouter:
    """Plan a truthful capability route without invoking the selected provider."""

    def __init__(self, registry: CapabilityWorkerRegistry) -> None:
        self.registry = registry

    def plan_route(
        self,
        state: CampaignEngineState,
        *,
        job_id: str,
        route_id: str,
        policy: WorkerSelectionPolicy | None = None,
    ) -> CampaignEngineState:
        if state.stage is not CampaignEngineStage.ASSET_PRODUCTION:
            raise CampaignEngineError("production routing requires the asset-production stage")
        if state.production_plan is None:
            raise CampaignEngineError("production routing requires a Production Plan")
        job = next(
            (item for item in state.production_plan.jobs if item.job_id == job_id),
            None,
        )
        if job is None:
            raise CampaignEngineError("production route references an unknown job")
        resolution = self.registry.resolve(
            job.required_capability,
            side_effect="preparation",
            policy=policy,
        )
        metadata = resolution.registration.metadata
        route = ProductionJobRoute(
            route_id=route_id,
            job_id=job.job_id,
            required_capability=job.required_capability,
            worker_id=metadata.worker_id,
            provider=metadata.provider,
            policy_id=resolution.policy_id,
            selection_reason=resolution.reason,
            source_production_pack_checksum=state.production_plan.production_pack.checksum,
        )
        return CampaignEngine().register_production_route(state, route)
