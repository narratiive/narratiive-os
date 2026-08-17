from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw import tony_live_bridge
from runtime.tony_delivery_blueprint_review import TonyDeliveryBlueprintReviewCommandService
from runtime.tony_delivery_commissioning import TonyDeliveryCommissioningCommandService
from runtime.tony_drive_delivery_workspace import TonyDriveDeliveryWorkspaceCommandService
from runtime.tony_verified_execution_status import TonyVerifiedExecutionStatusCommandService


class TonyLiveDeliveryCommissioningCompositionTests(unittest.TestCase):
    def test_live_bridge_composes_delivery_blueprint_review_after_commissioning(self):
        base_app = mock.Mock()
        base_service = mock.Mock()
        base_app.command_service = base_service
        base_app.bridge_token = ""
        base_app.brief_archive = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "TONY_INBOUND_LEADS_PATH": str(Path(tmp) / "leads.json"),
                "TONY_AGENCY_FOCUS_CONTEXT_PATH": str(Path(tmp) / "focus.json"),
                "TONY_EXECUTIVE_OUTCOMES_PATH": str(Path(tmp) / "outcomes.json"),
                "TONY_EXECUTIVE_LEARNING_PATH": str(Path(tmp) / "learning.json"),
                "TONY_POST_SEND_NOTION_SYNC_PATH": str(Path(tmp) / "post-send.json"),
                "TONY_MEETING_BOOKING_PATH": str(Path(tmp) / "meeting.json"),
                "TONY_POST_BOOKING_NOTION_SYNC_PATH": str(Path(tmp) / "booking-sync.json"),
                "TONY_DISCOVERY_OUTCOME_TRACKING_PATH": str(Path(tmp) / "discovery.json"),
                "TONY_POST_DISCOVERY_COMMERCIAL_PATH": str(Path(tmp) / "post-discovery.json"),
                "TONY_POST_DISCOVERY_PROPOSAL_EXECUTION_PATH": str(Path(tmp) / "proposal.json"),
                "TONY_PROPOSAL_OUTCOME_TRACKING_PATH": str(Path(tmp) / "proposal-outcome.json"),
                "TONY_COMMERCIAL_CLOSE_PATH": str(Path(tmp) / "close.json"),
                "TONY_DELIVERY_BOOTSTRAP_PATH": str(Path(tmp) / "delivery.json"),
                "TONY_DRIVE_DELIVERY_WORKSPACE_PATH": str(Path(tmp) / "drive.json"),
                "TONY_DELIVERY_COMMISSIONING_PATH": str(Path(tmp) / "commission.json"),
                "TONY_DELIVERY_BLUEPRINT_REVIEW_PATH": str(Path(tmp) / "blueprint-review.json"),
            }
            with mock.patch.object(tony_live_bridge, "build_base_app", return_value=base_app), mock.patch.dict(
                "os.environ", env, clear=True
            ):
                app = tony_live_bridge.build_app()

        execution_status = app.command_service.command_service
        self.assertIsInstance(execution_status, TonyVerifiedExecutionStatusCommandService)
        blueprint_review = execution_status.command_service
        self.assertIsInstance(blueprint_review, TonyDeliveryBlueprintReviewCommandService)
        self.assertEqual(blueprint_review.dispatchers, {})
        commissioning = blueprint_review.command_service
        self.assertIsInstance(commissioning, TonyDeliveryCommissioningCommandService)
        self.assertEqual(commissioning.dispatchers, {})
        self.assertIsInstance(commissioning.command_service, TonyDriveDeliveryWorkspaceCommandService)

    def test_live_bridge_passes_configured_claude_dispatcher_to_delivery_layers(self):
        base_app = mock.Mock()
        base_service = mock.Mock()
        base_app.command_service = base_service
        base_app.bridge_token = ""
        base_app.brief_archive = mock.Mock()
        fake_dispatcher = lambda dispatch: {"verified": True, "work_product": "x", "evidence_gaps": []}
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "TONY_INBOUND_LEADS_PATH": str(Path(tmp) / "leads.json"),
                "TONY_DELIVERY_COMMISSIONING_PATH": str(Path(tmp) / "commission.json"),
                "TONY_DELIVERY_BLUEPRINT_REVIEW_PATH": str(Path(tmp) / "blueprint-review.json"),
            }
            with mock.patch.object(tony_live_bridge, "build_base_app", return_value=base_app), mock.patch.object(
                tony_live_bridge, "build_http_dispatchers", return_value={"Claude": fake_dispatcher}
            ), mock.patch.dict("os.environ", env, clear=True):
                app = tony_live_bridge.build_app()

        blueprint_review = app.command_service.command_service.command_service
        self.assertIs(blueprint_review.dispatchers["Claude"], fake_dispatcher)
        commissioning = blueprint_review.command_service
        self.assertIs(commissioning.dispatchers["Claude"], fake_dispatcher)


if __name__ == "__main__":
    unittest.main()
