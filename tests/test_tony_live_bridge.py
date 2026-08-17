from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw import tony_live_bridge
from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_commercial_close import TonyCommercialCloseCommandService
from runtime.tony_commercial_followup import TonyCommercialFollowupCommandService
from runtime.tony_commercial_watch import TonyCommercialWatchCommandService
from runtime.tony_confirmed_meeting_booking import TonyConfirmedMeetingBookingCommandService
from runtime.tony_delivery_bootstrap import TonyDeliveryBootstrapCommandService
from runtime.tony_discovery_outcome_tracking import TonyDiscoveryOutcomeTrackingCommandService
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
    def _build(self, tmp, extra=None):
        base_app=mock.Mock(); base_service=mock.Mock(); base_app.command_service=base_service; base_app.bridge_token=""; base_app.brief_archive=mock.Mock()
        env={"TONY_INBOUND_LEADS_PATH":str(Path(tmp)/"leads.json"),"TONY_AGENCY_FOCUS_CONTEXT_PATH":str(Path(tmp)/"focus.json"),"TONY_EXECUTIVE_OUTCOMES_PATH":str(Path(tmp)/"outcomes.json"),"TONY_EXECUTIVE_LEARNING_PATH":str(Path(tmp)/"learning.json"),"TONY_POST_SEND_NOTION_SYNC_PATH":str(Path(tmp)/"post-send-sync.json"),"TONY_MEETING_BOOKING_PATH":str(Path(tmp)/"meeting-booking.json"),"TONY_POST_BOOKING_NOTION_SYNC_PATH":str(Path(tmp)/"post-booking-sync.json"),"TONY_DISCOVERY_OUTCOME_TRACKING_PATH":str(Path(tmp)/"discovery-outcome.json"),"TONY_POST_DISCOVERY_COMMERCIAL_PATH":str(Path(tmp)/"post-discovery.json"),"TONY_POST_DISCOVERY_PROPOSAL_EXECUTION_PATH":str(Path(tmp)/"proposal-execution.json"),"TONY_PROPOSAL_OUTCOME_TRACKING_PATH":str(Path(tmp)/"proposal-outcome.json"),"TONY_COMMERCIAL_CLOSE_PATH":str(Path(tmp)/"commercial-close.json"),"TONY_DELIVERY_BOOTSTRAP_PATH":str(Path(tmp)/"delivery-bootstrap.json")}; env.update(extra or {})
        with mock.patch.object(tony_live_bridge,"build_base_app",return_value=base_app), mock.patch.dict("os.environ",env,clear=True): app=tony_live_bridge.build_app()
        return app,base_app,base_service

    def test_build_app_composes_terminology_dispatch_memory_focus_commercial_capability_and_executive_commands(self):
        with tempfile.TemporaryDirectory() as tmp: app,base_app,base_service=self._build(tmp)
        self.assertIs(app.base,base_app); self.assertIsInstance(app.command_service,TonyTerminologyCommandService)
        execution_status=app.command_service.command_service; self.assertIsInstance(execution_status,TonyVerifiedExecutionStatusCommandService)
        delivery=execution_status.command_service; self.assertIsInstance(delivery,TonyDeliveryBootstrapCommandService); self.assertEqual(delivery.dispatchers,{})
        commercial_close=delivery.command_service; self.assertIsInstance(commercial_close,TonyCommercialCloseCommandService); self.assertEqual(commercial_close.dispatchers,{})
        proposal_outcome=commercial_close.command_service; self.assertIsInstance(proposal_outcome,TonyProposalOutcomeTrackingCommandService); self.assertEqual(proposal_outcome.dispatchers,{})
        proposal=proposal_outcome.command_service; self.assertIsInstance(proposal,TonyPostDiscoveryProposalExecutionCommandService); self.assertEqual(proposal.dispatchers,{})
        post_discovery=proposal.command_service; self.assertIsInstance(post_discovery,TonyPostDiscoveryCommercialCommandService); self.assertEqual(post_discovery.dispatchers,{})
        discovery=post_discovery.command_service; self.assertIsInstance(discovery,TonyDiscoveryOutcomeTrackingCommandService); self.assertEqual(discovery.dispatchers,{})
        booking_sync=discovery.command_service; self.assertIsInstance(booking_sync,TonyPostBookingNotionSyncCommandService); self.assertEqual(booking_sync.dispatchers,{})
        booking=booking_sync.command_service; self.assertIsInstance(booking,TonyConfirmedMeetingBookingCommandService); self.assertEqual(booking.dispatchers,{})
        meeting=booking.command_service; self.assertIsInstance(meeting,TonyMeetingReplyPreparationCommandService); self.assertEqual(meeting.dispatchers,{})
        followup=meeting.command_service; self.assertIsInstance(followup,TonyCommercialFollowupCommandService)
        post_send_sync=followup.command_service; self.assertIsInstance(post_send_sync,TonyPostSendNotionSyncCommandService); self.assertEqual(post_send_sync.dispatchers,{})
        dispatch=post_send_sync.command_service; self.assertIsInstance(dispatch,TonyAutonomousDispatchCommandService); self.assertEqual(dispatch.dispatchers,{})
        memory=dispatch.command_service; self.assertIsInstance(memory,TonyMemoryCommandService)
        adaptive=memory.command_service; self.assertIsInstance(adaptive,TonyAdaptiveResponseCommandService)
        learning=adaptive.command_service; self.assertIsInstance(learning,TonyExecutiveLearningCommandService)
        outcome_evidence=learning.command_service; self.assertIsInstance(outcome_evidence,TonyOutcomeEvidenceCommandService)
        outcomes=outcome_evidence.command_service; self.assertIsInstance(outcomes,TonyOutcomeAccountabilityCommandService)
        focus=outcomes.command_service; self.assertIsInstance(focus,TonyPersistentAgencyFocusCommandService)
        commercial_watch=focus.command_service; self.assertIsInstance(commercial_watch,TonyCommercialWatchCommandService)
        capability=commercial_watch.command_service; self.assertIsInstance(capability,TonyCapabilityCommandService)
        executive=capability.command_service; self.assertIsInstance(executive,TonyExecutiveCommandService); self.assertIs(executive.command_service,base_service)

    def test_build_app_configures_explicit_live_dispatchers(self):
        with tempfile.TemporaryDirectory() as tmp: app,_,_=self._build(tmp,{"TONY_DISPATCH_GMAIL_URL":"http://127.0.0.1:9999/gmail/read","TONY_DISPATCH_FIREFLIES_URL":"http://127.0.0.1:9999/fireflies/read","TONY_DISPATCH_NOTION_URL":"http://127.0.0.1:9999/notion/write"})
        execution_status=app.command_service.command_service
        delivery=execution_status.command_service; self.assertIsInstance(delivery,TonyDeliveryBootstrapCommandService); self.assertEqual(set(delivery.dispatchers),{"Gmail","Fireflies","Notion"})
        commercial_close=delivery.command_service; self.assertIsInstance(commercial_close,TonyCommercialCloseCommandService); self.assertEqual(set(commercial_close.dispatchers),{"Gmail","Fireflies","Notion"})
        proposal_outcome=commercial_close.command_service; self.assertIsInstance(proposal_outcome,TonyProposalOutcomeTrackingCommandService); self.assertEqual(set(proposal_outcome.dispatchers),{"Gmail","Fireflies","Notion"})
        proposal=proposal_outcome.command_service; self.assertIsInstance(proposal,TonyPostDiscoveryProposalExecutionCommandService); self.assertEqual(set(proposal.dispatchers),{"Gmail","Fireflies","Notion"})
        post_discovery=proposal.command_service; self.assertIsInstance(post_discovery,TonyPostDiscoveryCommercialCommandService); self.assertEqual(set(post_discovery.dispatchers),{"Gmail","Fireflies","Notion"})
        discovery=post_discovery.command_service; self.assertIsInstance(discovery,TonyDiscoveryOutcomeTrackingCommandService); self.assertEqual(set(discovery.dispatchers),{"Gmail","Fireflies","Notion"})
        booking_sync=discovery.command_service; self.assertIsInstance(booking_sync,TonyPostBookingNotionSyncCommandService); self.assertEqual(set(booking_sync.dispatchers),{"Gmail","Fireflies","Notion"})
        booking=booking_sync.command_service; self.assertIsInstance(booking,TonyConfirmedMeetingBookingCommandService); self.assertEqual(set(booking.dispatchers),{"Gmail","Fireflies","Notion"})
        meeting=booking.command_service; self.assertIsInstance(meeting,TonyMeetingReplyPreparationCommandService); self.assertEqual(set(meeting.dispatchers),{"Gmail","Fireflies","Notion"})
        followup=meeting.command_service; self.assertIsInstance(followup,TonyCommercialFollowupCommandService)
        post_send_sync=followup.command_service; self.assertEqual(set(post_send_sync.dispatchers),{"Gmail","Fireflies","Notion"}); dispatch=post_send_sync.command_service; self.assertEqual(set(dispatch.dispatchers),{"Gmail","Fireflies","Notion"})

    def test_build_app_preserves_mission_control_health_configuration(self):
        base_app=mock.Mock(); base_service=mock.Mock(); loader=mock.Mock(); base_service.mission_control_loader=loader; base_app.command_service=base_service; base_app.bridge_token=""; base_app.brief_archive=mock.Mock()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tony_live_bridge,"build_base_app",return_value=base_app), mock.patch.dict("os.environ",{"TONY_INBOUND_LEADS_PATH":str(Path(tmp)/"leads.json"),"TONY_AGENCY_FOCUS_CONTEXT_PATH":str(Path(tmp)/"focus.json"),"TONY_EXECUTIVE_OUTCOMES_PATH":str(Path(tmp)/"outcomes.json"),"TONY_EXECUTIVE_LEARNING_PATH":str(Path(tmp)/"learning.json"),"TONY_POST_SEND_NOTION_SYNC_PATH":str(Path(tmp)/"sync.json"),"TONY_MEETING_BOOKING_PATH":str(Path(tmp)/"meeting-booking.json"),"TONY_POST_BOOKING_NOTION_SYNC_PATH":str(Path(tmp)/"post-booking.json"),"TONY_DISCOVERY_OUTCOME_TRACKING_PATH":str(Path(tmp)/"discovery.json"),"TONY_POST_DISCOVERY_COMMERCIAL_PATH":str(Path(tmp)/"post-discovery.json"),"TONY_POST_DISCOVERY_PROPOSAL_EXECUTION_PATH":str(Path(tmp)/"proposal-execution.json"),"TONY_PROPOSAL_OUTCOME_TRACKING_PATH":str(Path(tmp)/"proposal-outcome.json"),"TONY_COMMERCIAL_CLOSE_PATH":str(Path(tmp)/"commercial-close.json"),"TONY_DELIVERY_BOOTSTRAP_PATH":str(Path(tmp)/"delivery-bootstrap.json")},clear=True): app=tony_live_bridge.build_app()
        self.assertIs(app.command_service.mission_control_loader,loader)

    def test_lead_ingestion_is_authenticated_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_app=mock.Mock(); base_app.bridge_token="secret"; base_app.command_service=mock.Mock(); base_app.brief_archive=mock.Mock(); store=tony_live_bridge.FileInboundLeadStore(Path(tmp)/"leads.json"); app=tony_live_bridge.LeadAwareTonyApplication(base_app,store)
            payload=json.dumps({"lead_id":"lead-1","contact":"Steve","company":"Steve Company","source":"Growth Diagnostic","status":"New"}).encode(); environ={"REQUEST_METHOD":"POST","PATH_INFO":"/leads/ingest","CONTENT_LENGTH":str(len(payload)),"CONTENT_TYPE":"application/json","HTTP_AUTHORIZATION":"Bearer secret","wsgi.input":io.BytesIO(payload)}; status={}
            response=app(environ,lambda value,headers:status.update(value=value,headers=headers)); self.assertTrue(status["value"].startswith("200")); self.assertTrue(json.loads(b"".join(response))["ok"]); self.assertEqual(store.read()[0].contact,"Steve")

    def test_build_app_fails_closed_without_command_service(self):
        base_app=mock.Mock(); base_app.command_service=None
        with mock.patch.object(tony_live_bridge,"build_base_app",return_value=base_app):
            with self.assertRaisesRegex(RuntimeError,"not configured"): tony_live_bridge.build_app()


if __name__=="__main__": unittest.main()