from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from runtime.campaign_engine import CampaignIdentity
from runtime.campaign_learning import (
    CampaignLearningCycle,
    CampaignLearningError,
    CampaignLearningService,
    FileCampaignLearningStore,
)
from runtime.campaign_learning_projection import CampaignLearningProjectionService
from runtime.media_control import CanonicalMediaSnapshot, MediaControlService
from runtime.models import WorkflowState


class CampaignLearningCoordinator:
    """Join approved asset lineage to read-only media evidence.

    This is an orchestration boundary only: it persists internal evidence and can
    prepare a Notion projection. The projection write remains separately bound
    to Matt's identity, rationale and the exact learning-cycle checksum.
    """

    def __init__(
        self,
        root: str | Path,
        media_control: MediaControlService,
        *,
        notion_dispatcher=None,
    ) -> None:
        self.root = Path(root)
        self.media_control = media_control
        self.learning = CampaignLearningService()
        self.store = FileCampaignLearningStore(self.root / "cycles")
        self.projection = CampaignLearningProjectionService(
            self.root / "notion-projection",
            notion_dispatcher,
        )

    def prepare(self, states: Iterable[WorkflowState], query: str) -> dict[str, Any]:
        cycle = self._cycle(tuple(states), query)
        return self._prepare_cycle(cycle)

    def _prepare_cycle(self, cycle: CampaignLearningCycle) -> dict[str, Any]:
        location = self.store.persist(cycle)
        projection = self.projection.prepare(cycle)
        return {
            **cycle.to_dict(),
            "cycle_location": str(location),
            "projection_status": projection["projection_status"],
            "projection_key": projection["projection_key"],
            "recommended_next_action": (
                "Matt reviews the evidence-graded insights and any bounded creative iteration proposal."
            ),
        }

    def sync(
        self,
        states: Iterable[WorkflowState],
        query: str,
        *,
        cycle_checksum: str,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        cycle = self._cycle(tuple(states), query)
        if not cycle_checksum.strip() or cycle_checksum.strip() != cycle.checksum:
            raise CampaignLearningError("learning approval is stale or is not bound to the exact cycle checksum")
        self.store.persist(cycle)
        return self.projection.sync(cycle, approver=approver, rationale=rationale)

    def _cycle(self, states: Iterable[WorkflowState], query: str) -> CampaignLearningCycle:
        states = tuple(states)
        snapshots = self._snapshots(query)
        return self._cycle_from_snapshots(states, snapshots)

    def _cycle_from_snapshots(
        self,
        states: Iterable[WorkflowState],
        snapshots: Sequence[CanonicalMediaSnapshot],
    ) -> CampaignLearningCycle:
        identity = snapshots[0].identity
        self._require_fulfilment(states, identity.client_id, identity.campaign_id)
        approved_ids = self._approved_asset_versions(states, identity.client_id, identity.campaign_id)
        recommendations = self.media_control.analyse(snapshots)
        return self.learning.build(
            snapshots,
            recommendations,
            approved_asset_version_ids=approved_ids,
        )

    def monitor(self, states: Iterable[WorkflowState]) -> dict[str, Any]:
        """Prepare every currently observable campaign without external writes."""

        states = tuple(states)
        grouped: dict[CampaignIdentity, list[CanonicalMediaSnapshot]] = defaultdict(list)
        for snapshot in self.media_control.snapshots():
            grouped[snapshot.identity].append(snapshot)
        results = []
        for identity in sorted(grouped, key=lambda item: (item.client_id, item.campaign_id)):
            candidates = grouped[identity]
            latest_period = max((item.period_start, item.period_end) for item in candidates)
            snapshots = tuple(
                item for item in candidates
                if (item.period_start, item.period_end) == latest_period
            )
            try:
                providers = [snapshot.provider for snapshot in snapshots]
                if len(providers) != len(set(providers)):
                    raise CampaignLearningError("latest campaign evidence contains duplicate provider snapshots")
                prepared = self._prepare_cycle(self._cycle_from_snapshots(states, snapshots))
            except (CampaignLearningError, ValueError) as exc:
                results.append({
                    "client_id": identity.client_id,
                    "campaign_id": identity.campaign_id,
                    "status": "blocked",
                    "reason": str(exc),
                    "external_action_taken": False,
                })
            else:
                results.append({
                    "client_id": identity.client_id,
                    "campaign_id": identity.campaign_id,
                    "status": "ready_for_matt_review",
                    "cycle_id": prepared["cycle_id"],
                    "cycle_checksum": prepared["checksum"],
                    "insight_count": len(prepared["insights"]),
                    "iteration_proposal_count": len(prepared["iteration_proposals"]),
                    "projection_status": prepared["projection_status"],
                    "external_action_taken": False,
                })
        return {
            "campaigns": results,
            "campaign_count": len(results),
            "ready_count": sum(item["status"] == "ready_for_matt_review" for item in results),
            "blocked_count": sum(item["status"] == "blocked" for item in results),
            "external_action_taken": False,
        }

    def _snapshots(self, query: str) -> tuple[CanonicalMediaSnapshot, ...]:
        needle = query.strip().casefold()
        if not needle:
            raise CampaignLearningError("campaign learning requires a client or campaign reference")
        matched = tuple(
            snapshot
            for snapshot in self.media_control.snapshots()
            if needle in {
                snapshot.identity.client_id.casefold(),
                snapshot.identity.brand_id.casefold(),
                snapshot.identity.campaign_id.casefold(),
            }
        )
        identities = {snapshot.identity for snapshot in matched}
        if not matched:
            raise CampaignLearningError("no verified media snapshot matched the campaign reference")
        if len(identities) != 1:
            raise CampaignLearningError("campaign learning reference is ambiguous")
        latest_period = max((snapshot.period_start, snapshot.period_end) for snapshot in matched)
        latest = tuple(
            snapshot for snapshot in matched
            if (snapshot.period_start, snapshot.period_end) == latest_period
        )
        providers = [snapshot.provider for snapshot in latest]
        if len(providers) != len(set(providers)):
            raise CampaignLearningError("latest campaign evidence contains duplicate provider snapshots")
        return latest

    @staticmethod
    def _require_fulfilment(
        states: Iterable[WorkflowState], client_id: str, campaign_id: str
    ) -> None:
        for state in states:
            if state.client_id != client_id or state.workflow_id != "delivery_to_follow_up_next_action":
                continue
            identity = state.input_payload.get("campaign_identity")
            if not isinstance(identity, Mapping) or str(identity.get("campaign_id") or "") != campaign_id:
                continue
            if state.status.value == "complete" and state.approval_status == "approved":
                return
        raise CampaignLearningError(
            "campaign learning waits for completed delivery follow-up and explicit human approval"
        )

    @staticmethod
    def _approved_asset_versions(
        states: Iterable[WorkflowState], client_id: str, campaign_id: str
    ) -> tuple[str, ...]:
        candidates: list[tuple[str, tuple[str, ...]]] = []
        for state in states:
            if state.client_id != client_id or state.workflow_id != "creative_bible_to_asset_production":
                continue
            identity = state.input_payload.get("campaign_identity")
            if not isinstance(identity, Mapping) or str(identity.get("campaign_id") or "") != campaign_id:
                continue
            decisions = [
                item for item in state.approval_history
                if item.get("decision") == "asset_suite_approval"
            ]
            if not decisions:
                continue
            exact_ids = tuple(
                str(item).strip() for item in decisions[-1].get("asset_version_ids", ())
                if str(item).strip()
            )
            if exact_ids:
                candidates.append((state.updated_at, exact_ids))
        if not candidates:
            raise CampaignLearningError(
                "campaign learning requires a matching human-approved asset suite"
            )
        return max(candidates, key=lambda item: item[0])[1]
