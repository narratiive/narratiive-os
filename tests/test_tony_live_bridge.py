from __future__ import annotations
import io,json,tempfile,unittest
from pathlib import Path
from unittest import mock
from openclaw import tony_live_bridge
from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_blueprint_client_delivery import TonyBlueprintClientDeliveryCommandService
from runtime.tony_blueprint_delivery_notion_sync import TonyBlueprintDeliveryNotionSyncCommandService
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_commercial_close import TonyCommercialCloseCommandService
from runtime.tony_commercial_followup import TonyCommercialFollowupCommandService
from runtime.tony_commercial_watch import TonyCommercialWatchCommandService
from runtime.tony_confirmed_meeting_booking import TonyConfirmedMeetingBookingCommandService
from runtime.tony_delivery_blueprint_review import TonyDeliveryBlueprintReviewCommandService
from runtime.tony_delivery_bootstrap import TonyDeliveryBootstrapCommandService
from runtime.tony_delivery_commissioning import TonyDeliveryCommissioningCommandService
from runtime.tony_discovery_outcome_tracking import TonyDiscoveryOutcomeTrackingCommandService
from runtime.tony_drive_delivery_workspace import TonyDriveDeliveryWorkspaceCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService
from runtime.tony_executive_learning import TonyExecutiveLearningCommandService
from runtime.tony_meeting_reply_preparation import TonyMeetingReplyPreparationCommandService
from runtime.tony_memory_commands import TonyMemoryCommandService
from runtime.tony_outcome_accountability import TonyOutcomeAccountabilityCommandService
from runtime.tony_outcome_evidence import TonyOutcomeEvidenceCommandService
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService
from runtime.tony_post_booking_notion_sync import TonyPostBookingNotionSyncCommandService
from runtime.tony_post_discovery_commercial import TonyPostDiscoveryCommercialCommandService
from runtime.tony_post_discovery_proposal_execution import TonyPostDiscoveryProposalExecutionCommandService
from runtime.tony_post_send_notion_sync import TonyPostSendNotionSyncCommandService
from runtime.tony_proposal_outcome_tracking import TonyProposalOutcomeTrackingCommandService
from runtime.tony_terminology_commands import TonyTerminologyCommandService
from runtime.tony_verified_execution_status import TonyVerifiedExecutionStatusCommandService

class TonyLiveBridgeTests(unittest.TestCase):
    def _build(self,tmp,extra=None):
        base_app=mock.Mock(); base_service=mock.Mock(); base_app.command_service=base_service; base_app.bridge_token=""; base_app.brief_archive=mock.Mock()
        env={"TONY_INBOUND_LEADS_PATH":str(Path(tmp)/"leads.json"),"TONY_AGENCY_FOCUS_CONTEXT_PATH":str(Path(tmp)/"focus.json"),"TONY_EXECUTIVE_OUTCOMES_PATH":str(Path(tmp)/"outcomes.json"),"TONY_EXECUTIVE_LEARNING_PATH":str(Path(tmp)/"learning.json"),"TONY_POST_SEND_NOTION_SYNC_PATH":str(Path(tmp)/"post-send.json"),"TONY_MEETING_BOOKING_PATH":str(Path(tmp)/"meeting.json"),"TONY_POST_BOOKING_NOTION_SYNC_PATH":str(Path(tmp)/"booking-sync.json"),"TONY_DISCOVERY_OUTCOME_TRACKING_PATH":str(Path(tmp)/"discovery.json"),"TONY_POST_DISCOVERY_COMMERCIAL_PATH":str(Path(tmp)/"post-discovery.json"),"TONY_POST_DISCOVERY_PROPOSAL_EXECUTION_PATH":str(Path(tmp)/"proposal.json"),"TONY_PROPOSAL_OUTCOME_TRACKING_PATH":str(Path(tmp)/"proposal-outcome.json"),"TONY_COMMERCIAL_CLOSE_PATH":str(Path(tmp)/"close.json"),"TONY_DELIVERY_BOOTSTRAP_PATH":str(Path(tmp)/"delivery.json"),"TONY_DRIVE_DELIVERY_WORKSPACE_PATH":str(Path(tmp)/"drive.json"),"TONY_DELIVERY_COMMISSIONING_PATH":str(Path(tmp)/"commission.json"),"TONY_DELIVERY_BLUEPRINT_REVIEW_PATH":str(Path(tmp)/"blueprint-review.json"),"TONY_BLUEPRINT_CLIENT_DELIVERY_PATH":str(Path(tmp)/"blueprint-delivery.json"),"TONY_BLUEPRINT_DELIVERY_NOTION_SYNC_PATH":str(Path(tmp)/"blueprint-delivery-sync.json")}; env.update(extra or {})
        with mock.patch.object(tony_live_bridge,"build_base_app",return_value=base_app),mock.patch.dict("os.environ",env,clear=True): app=tony_live_bridge.build_app()
        return app,base_app,base_service
    def test_build_app_composes_terminology_dispatch_memory_focus_commercial_capability_and_executive_commands(self):
        with tempfile.TemporaryDirectory() as tmp: app,base_app,base_service=self._build(tmp)
        self.assertIs(app.base,base_app); self.assertIsInstance(app.command_service,TonyTerminologyCommandService); execution_status=app.command_service.command_service; self.assertIsInstance(execution_status,TonyVerifiedExecutionStatusCommandService)
        notion_sync=execution_status.command_service; self.assertIsInstance(notion_sync,TonyBlueprintDeliveryNotionSyncCommandService); self.assertEqual(notion_sync.dispatchers,{})
        client_delivery=notion_sync.command_service; self.assertIsInstance(client_delivery,TonyBlueprintClientDeliveryCommandService); self.assertEqual(client_delivery.dispatchers,{})
        blueprint=client_delivery.command_service; self.assertIsInstance(blueprint,TonyDeliveryBlueprintReviewCommandService); self.assertEqual(blueprint.dispatchers,{})
        commissioning=blueprint.command_service; self.assertIsInstance(commissioning,TonyDeliveryCommissioningCommandService); self.assertEqual(commissioning.dispatchers,{})
        drive=commissioning.command_service; self.assertIsInstance(drive,TonyDriveDeliveryWorkspaceCommandService); self.assertEqual(drive.dispatchers,{})
        delivery=drive.command_service; self.assertIsInstance(delivery,TonyDeliveryBootstrapCommandService); commercial_close=delivery.command_service; self.assertIsInstance(commercial_close,TonyCommercialCloseCommandService); proposal_outcome=commercial_close.command_service; self.assertIsInstance(proposal_outcome,TonyProposalOutcomeTrackingCommandService); proposal=proposal_outcome.command_service; self.assertIsInstance(proposal,TonyPostDiscoveryProposalExecutionCommandService); post_discovery=proposal.command_service; self.assertIsInstance(post_discovery,TonyPostDiscoveryCommercialCommandService); discovery=post_discovery.command_service; self.assertIsInstance(discovery,TonyDiscoveryOutcomeTrackingCommandService); booking_sync=discovery.command_service; self.assertIsInstance(booking_sync,TonyPostBookingNotionSyncCommandService); booking=booking_sync.command_service; self.assertIsInstance(booking,TonyConfirmedMeetingBookingCommandService); meeting=booking.command_service; self.assertIsInstance(meeting,TonyMeetingReplyPreparationCommandService); followup=meeting.command_service; self.assertIsInstance(followup,TonyCommercialFollowupCommandService); post_send=followup.command_service; self.assertIsInstance(post_send,TonyPostSendNotionSyncCommandService); dispatch=post_send.command_service; self.assertIsInstance(dispatch,TonyAutonomousDispatchCommandService); memory=dispatch.command_service; self.assertIsInstance(memory,TonyMemoryCommandService); adaptive=memory.command_service; self.assertIsInstance(adaptive,TonyAdaptiveResponseCommandService); learning=adaptive.command_service; self.assertIsInstance(learning,TonyExecutiveLearningCommandService); outcome_evidence=learning.command_service; self.assertIsInstance(outcome_evidence,TonyOutcomeEvidenceCommandService); outcomes=outcome_evidence.command_service; self.assertIsInstance(outcomes,TonyOutcomeAccountabilityCommandService); focus=outcomes.command_service; self.assertIsInstance(focus,TonyPersistentAgencyFocusCommandService); watch=focus.command_service; self.assertIsInstance(watch,TonyCommercialWatchCommandService); capability=watch.command_service; self.assertIsInstance(capability,TonyCapabilityCommandService); executive=capability.command_service; self.assertIsInstance(executive,TonyExecutiveCommandService); self.assertIs(executive.command_service,base_service)
    def test_build_app_configures_explicit_live_dispatchers(self):
        with tempfile.TemporaryDirectory() as tmp: app,_,_=self._build(tmp,{"TONY_DISPATCH_GMAIL_URL":"http://127.0.0.1:9999/gmail","TONY_DISPATCH_FIREFLIES_URL":"http://127.0.0.1:9999/fireflies","TONY_DISPATCH_NOTION_URL":"http://127.0.0.1:9999/notion","TONY_DISPATCH_GOOGLE_DRIVE_URL":"http://127.0.0.1:9999/drive"})
        execution_status=app.command_service.command_service; notion_sync=execution_status.command_service; self.assertIsInstance(notion_sync,TonyBlueprintDeliveryNotionSyncCommandService); self.assertEqual(set(notion_sync.dispatchers),{"Gmail","Fireflies","Notion","Google Drive"}); client_delivery=notion_sync.command_service; self.assertIsInstance(client_delivery,TonyBlueprintClientDeliveryCommandService); self.assertEqual(set(client_delivery.dispatchers),{"Gmail","Fireflies","Notion","Google Drive"}); blueprint=client_delivery.command_service; self.assertIsInstance(blueprint,TonyDeliveryBlueprintReviewCommandService); self.assertEqual(set(blueprint.dispatchers),{"Gmail","Fireflies","Notion","Google Drive"}); commissioning=blueprint.command_service; self.assertIsInstance(commissioning,TonyDeliveryCommissioningCommandService); self.assertEqual(set(commissioning.dispatchers),{"Gmail","Fireflies","Notion","Google Drive"}); drive=commissioning.command_service; self.assertIsInstance(drive,TonyDriveDeliveryWorkspaceCommandService); self.assertEqual(set(drive.dispatchers),{"Gmail","Fireflies","Notion","Google Drive"}); delivery=drive.command_service; self.assertIsInstance(delivery,TonyDeliveryBootstrapCommandService); self.assertEqual(set(delivery.dispatchers),{"Gmail","Fireflies","Notion","Google Drive"})
    def test_build_app_preserves_mission_control_health_configuration(self):
        base_app=mock.Mock(); base_service=mock.Mock(); loader=mock.Mock(); base_service.mission_control_loader=loader; base_app.command_service=base_service; base_app.bridge_token=""; base_app.brief_archive=mock.Mock()
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(tony_live_bridge,"build_base_app",return_value=base_app),mock.patch.dict("os.environ",{"TONY_INBOUND_LEADS_PATH":str(Path(tmp)/"leads.json")},clear=True): app=tony_live_bridge.build_app()
        self.assertIs(app.command_service.mission_control_loader,loader)
    def test_lead_ingestion_is_authenticated_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_app=mock.Mock(); base_app.bridge_token="secret"; base_app.command_service=mock.Mock(); base_app.brief_archive=mock.Mock(); store=tony_live_bridge.FileInboundLeadStore(Path(tmp)/"leads.json"); app=tony_live_bridge.LeadAwareTonyApplication(base_app,store); payload=json.dumps({"lead_id":"lead-1","contact":"Steve","company":"Steve Company","source":"Growth Diagnostic","status":"New"}).encode(); environ={"REQUEST_METHOD":"POST","PATH_INFO":"/leads/ingest","CONTENT_LENGTH":str(len(payload)),"CONTENT_TYPE":"application/json","HTTP_AUTHORIZATION":"Bearer secret","wsgi.input":io.BytesIO(payload)}; status={}; response=app(environ,lambda value,headers:status.update(value=value,headers=headers)); self.assertTrue(status["value"].startswith("200")); self.assertTrue(json.loads(b"".join(response))["ok"])
    def test_build_app_fails_closed_without_command_service(self):
        base_app=mock.Mock(); base_app.command_service=None
        with mock.patch.object(tony_live_bridge,"build_base_app",return_value=base_app):
            with self.assertRaisesRegex(RuntimeError,"not configured"): tony_live_bridge.build_app()
if __name__=="__main__": unittest.main()
