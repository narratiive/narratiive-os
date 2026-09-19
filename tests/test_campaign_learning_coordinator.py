from __future__ import annotations

import tempfile
import unittest

from runtime.campaign_learning import CampaignLearningError
from runtime.campaign_learning_coordinator import CampaignLearningCoordinator
from runtime.models import WorkflowState, WorkflowStatus
from tests.test_campaign_learning import ASSET_VERSION_ID, _snapshot_and_recommendations


class _Media:
    def __init__(self, snapshot, recommendations) -> None:
        self._snapshot = snapshot
        self._recommendations = recommendations

    def snapshots(self):
        return (self._snapshot,)

    def analyse(self, snapshots):
        if tuple(snapshots) != (self._snapshot,):
            raise AssertionError("coordinator analysed evidence outside the selected campaign")
        return self._recommendations


def _approved_state(snapshot) -> WorkflowState:
    return WorkflowState(
        workflow_id="creative_bible_to_asset_production",
        run_id="northstar-approved-assets",
        stages=[],
        workspace_id=snapshot.identity.workspace_id,
        client_id=snapshot.identity.client_id,
        entity_id=snapshot.identity.campaign_id,
        input_payload={
            "campaign_identity": {
                "workspace_id": snapshot.identity.workspace_id,
                "client_id": snapshot.identity.client_id,
                "brand_id": snapshot.identity.brand_id,
                "market_ids": list(snapshot.identity.market_ids),
                "product_ids": list(snapshot.identity.product_ids),
                "campaign_id": snapshot.identity.campaign_id,
            }
        },
        approval_status="approved",
        approval_history=[
            {
                "decision": "asset_suite_approval",
                "approver": "telegram:matt",
                "asset_version_ids": [ASSET_VERSION_ID],
            }
        ],
    )


def _fulfilled_state(snapshot) -> WorkflowState:
    return WorkflowState(
        workflow_id="delivery_to_follow_up_next_action",
        run_id="northstar-complete-follow-up",
        stages=[],
        status=WorkflowStatus.COMPLETE,
        workspace_id=snapshot.identity.workspace_id,
        client_id=snapshot.identity.client_id,
        entity_id=snapshot.identity.campaign_id,
        input_payload={
            "campaign_identity": {
                "campaign_id": snapshot.identity.campaign_id,
            }
        },
        approval_status="approved",
        approval_history=[{"decision": "approve", "approver": "telegram:matt"}],
    )


def _states(snapshot):
    return (_approved_state(snapshot), _fulfilled_state(snapshot))


class CampaignLearningCoordinatorTests(unittest.TestCase):
    def test_prepares_persisted_review_cycle_from_exact_approved_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(f"{directory}/media")
            coordinator = CampaignLearningCoordinator(
                f"{directory}/learning",
                _Media(snapshot, recommendations),
            )

            result = coordinator.prepare(_states(snapshot), snapshot.identity.campaign_id)
            replay = coordinator.prepare(_states(snapshot), snapshot.identity.campaign_id)

            self.assertEqual(result["checksum"], replay["checksum"])
            self.assertEqual(result["projection_status"], "prepared")
            self.assertTrue(result["insights"])
            self.assertTrue(result["iteration_proposals"])
            self.assertFalse(result["external_action_taken"])

    def test_missing_or_different_asset_approval_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(f"{directory}/media")
            coordinator = CampaignLearningCoordinator(
                f"{directory}/learning",
                _Media(snapshot, recommendations),
            )

            with self.assertRaisesRegex(CampaignLearningError, "human-approved asset suite"):
                coordinator.prepare((_fulfilled_state(snapshot),), snapshot.identity.campaign_id)

    def test_learning_before_completed_fulfilment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(f"{directory}/media")
            coordinator = CampaignLearningCoordinator(
                f"{directory}/learning",
                _Media(snapshot, recommendations),
            )

            with self.assertRaisesRegex(CampaignLearningError, "completed delivery follow-up"):
                coordinator.prepare((_approved_state(snapshot),), snapshot.identity.campaign_id)

    def test_notion_sync_requires_matt_and_exact_current_checksum(self) -> None:
        dispatches = []

        def notion(dispatch):
            dispatches.append(dispatch)
            return {
                "external_action_taken": True,
                "record_id": "northstar-learning-record",
                "projection_key": dispatch["idempotency_key"],
                "cycle_checksum": dispatch["payload"]["learning_cycle_checksum"],
            }

        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(f"{directory}/media")
            states = _states(snapshot)
            coordinator = CampaignLearningCoordinator(
                f"{directory}/learning",
                _Media(snapshot, recommendations),
                notion_dispatcher=notion,
            )
            preview = coordinator.prepare(states, snapshot.identity.campaign_id)

            with self.assertRaisesRegex(CampaignLearningError, "stale"):
                coordinator.sync(
                    states,
                    snapshot.identity.campaign_id,
                    cycle_checksum="wrong",
                    approver="telegram:matt",
                    rationale="Project verified learning.",
                )
            with self.assertRaisesRegex(ValueError, "Matt"):
                coordinator.sync(
                    states,
                    snapshot.identity.campaign_id,
                    cycle_checksum=preview["checksum"],
                    approver="tony",
                    rationale="Tony cannot approve strategic learning.",
                )
            synced = coordinator.sync(
                states,
                snapshot.identity.campaign_id,
                cycle_checksum=preview["checksum"],
                approver="matt:telegram:123",
                rationale="Project the exact reviewed learning cycle.",
            )
            replay = coordinator.sync(
                states,
                snapshot.identity.campaign_id,
                cycle_checksum=preview["checksum"],
                approver="matt:telegram:123",
                rationale="Replay safely.",
            )

            self.assertEqual(synced["projection_status"], "verified")
            self.assertEqual(replay["projection_status"], "duplicate_suppressed")
            self.assertEqual(len(dispatches), 1)

    def test_monitor_reports_ready_and_is_safe_to_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, recommendations = _snapshot_and_recommendations(f"{directory}/media")
            coordinator = CampaignLearningCoordinator(
                f"{directory}/learning",
                _Media(snapshot, recommendations),
            )

            first = coordinator.monitor(_states(snapshot))
            second = coordinator.monitor(_states(snapshot))

            self.assertEqual(first, second)
            self.assertEqual(first["ready_count"], 1)
            self.assertEqual(first["blocked_count"], 0)
            self.assertFalse(first["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
