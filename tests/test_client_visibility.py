import copy
import unittest
from types import SimpleNamespace
from runtime.models import WorkflowState, WorkflowStatus
from runtime.tony_workflow_commands import TonyWorkflowCommandService
from runtime.client_visibility import client_engagements, verified_review_link


def state(run, workflow='growth_blueprint_to_campaign_world', client='origin-id', workspace='narratiive', parent=None, **payload):
    if parent: payload['_lineage']={'parent_run_id':parent}
    return WorkflowState(workflow_id=workflow,run_id=run,workspace_id=workspace,client_id=client,
        entity_id=client,stages=[],status=WorkflowStatus.BLOCKED,input_payload=payload,
        blocker='worker_retry_policy_exhausted')


class ClientVisibilityTests(unittest.TestCase):
    def service(self, states):
        backend=SimpleNamespace(list_states=lambda:tuple(states), artifact_detail=lambda s: (_ for _ in ()).throw(ValueError('No review')))
        return TonyWorkflowCommandService(None, backend)

    def test_observed_origin_and_katkin_commands_use_workflow_records_without_mutation(self):
        origin=state('origin-current',client_context={'name':'Origin Coffee — FICTIONAL REHEARSAL','aliases':['Origin']})
        katkin=state('katkin-review','growth_blueprint_deliverable_production',client='katkin',company='KatKin')
        katkin.status=WorkflowStatus.AWAITING_APPROVAL;katkin.approval_status='pending'
        before=copy.deepcopy([origin,katkin]);service=self.service([origin,katkin])
        for command in ('/client Origin','/client oRiGiN','/workflow Origin','/client katkin','/clients'):
            result=service.execute(command, [])
            self.assertNotEqual(result.status,'error',command)
            self.assertNotIn('worker_retry_policy_exhausted',result.message)
            self.assertNotIn('growth_blueprint_to_campaign_world',result.message)
            self.assertNotIn('Blueprint Lite',result.message)
            self.assertIn('Matt:',result.message)
            self.assertIn('No verified current review link',result.message)
        self.assertIn('Sketchbook',service.execute('/client Origin',[]).message)
        self.assertIn('Fieldwork',service.execute('/client katkin',[]).message)
        self.assertEqual([origin,katkin],before)

    def test_lineage_collapses_stages_but_separate_engagements_remain_explicit_choices(self):
        first=state('research','growth_sprint_to_research_engine',company='Origin')
        child=state('creative',parent='research',company='Origin')
        other=state('separate',company='Origin')
        self.assertEqual(len(client_engagements([first,child],'Origin')),1)
        result=self.service([first,child,other]).execute('/client Origin',[])
        self.assertTrue(result.data['ambiguous']);self.assertEqual(len(result.data['clients']),2)
        self.assertIn('choose the engagement',result.message)

    def test_same_name_and_run_reference_in_other_workspace_never_merges(self):
        first=state('same',company='Origin')
        second=state('child',workspace='other',parent='same',company='Origin')
        self.assertEqual(len(client_engagements([first,second],'Origin')),2)
        self.assertEqual(client_engagements([first],'Origami'),())

    def test_distinct_campaigns_from_shared_parent_remain_choices(self):
        parent=state('shared','growth_blueprint_deliverable_production',company='Origin')
        first=state('campaign-a',parent='shared',company='Origin',campaign_identity={'campaign_id':'a'})
        second=state('campaign-b',parent='shared',company='Origin',campaign_identity={'campaign_id':'b'})
        self.assertEqual(len(client_engagements([parent,first,second],'Origin')),2)

    def test_review_link_requires_current_artifact_and_verified_pdf_manifest_binding(self):
        s=state('current',company='Origin')
        receipt={'kind':'internal_artifact_review_delivery','artifact_id':'current-artifact','artifact_checksum':'source-checksum',
            'review_artifact_checksum':'pdf-checksum','recipient':'hello@narratiive.com','message_id':'verified-message','thread_id':'verified-thread'}
        s.external_action_receipts=[{'receipt':receipt}]
        backend=SimpleNamespace(artifact_detail=lambda s:{'human_review_artifact':{'checksum':'pdf-checksum'},
            'approved_artifact':{'artifact_id':'current-artifact','artifact_checksum':'source-checksum'}})
        self.assertEqual(verified_review_link(s,backend),'https://mail.google.com/mail/u/0/#all/verified-thread')
        receipt['artifact_checksum']='stale';self.assertIsNone(verified_review_link(s,backend))
        receipt['artifact_checksum']='source-checksum';receipt['review_artifact_checksum']='old-pdf'
        self.assertIsNone(verified_review_link(s,backend))
