from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import tempfile
import unittest

from runtime.models import ArtifactRef, StageRecord, WorkflowState, WorkflowStatus
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.run_service import WorkflowRunService
from runtime.synthetic_rehearsal import SyntheticRehearsalService, PROPOSAL, ASSETS
from runtime.workflow_entity_classification import FileWorkflowEntityClassificationJournal, WorkflowEntityClassification, INTERNAL_SYNTHETIC_TEST, GENUINE_CLIENT
from runtime.campaign_production_planning_worker import CampaignProductionPlanningWorker
from runtime.workflow_quality import production_planning_quality_gate
from runtime.deliverable_production import build_quantified_commercial_model, commercial_model_quality_checks
from tests.test_campaign_production_planning_worker import planning_contract


class SyntheticRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        repository=FileWorkflowRunRepository(root/'runs',workspace_id='safe',client_id='safe-client')
        log=JsonlEventLog(root/'events',workspace_id='safe')
        self.runs=WorkflowRunService(repository,log,workspace_id='safe',client_id='safe-client')
        self.runtime=SimpleNamespace(runs=self.runs)
        self.journal=FileWorkflowEntityClassificationJournal(root,authorised_classifier_id='founder')
        artifact=ArtifactRef('proposal-safe','workflow_step_output','unused','a'*64,metadata={'version':4})
        self.proposal=WorkflowState(PROPOSAL,'safe-proposal',[StageRecord('draft','specialist',output_artifacts=[artifact])],
            status=WorkflowStatus.COMPLETE,approval_status='approved',workspace_id='safe',client_id='safe-client',entity_id='safe-entity')
        self.proposal.approval_history.append({'approver':'actual-human-founder','approved_at':'2026-11-05T10:00:00Z',
            'approval_binding':{'artifact_checksum':artifact.checksum,'human_decision':{
                'verbatim_current_human_instruction_verified':True,'explicit_decision_intent':'approve','scope':'fictional_rehearsal_only'}}})
        repository.save(self.proposal)
        self.service=SyntheticRehearsalService(self.runtime,self.journal,lambda:())

    def classify(self,classification=INTERNAL_SYNTHETIC_TEST):
        e=WorkflowEntityClassification.create(workspace_id='safe',entity_id='safe-entity',workflow_id=PROPOSAL,
            classification=classification,classifier_id='founder',authorisation_reference='actual-test-input',
            authorisation_turn_id='actual-test-turn',authorisation_proof='test-proof',reason='Explicit fictional rehearsal')
        self.journal.append(e,states=[self.proposal],principal_id='founder')

    def test_acceptance_is_scoped_append_only_idempotent_and_never_real_payment(self):
        self.classify()
        first=self.service.enrol(self.proposal,authorisation_reference='user:source',scope_instruction='Two stills, final Matt review')
        self.assertEqual(first,self.service.enrol(self.proposal,authorisation_reference='user:source',scope_instruction='Two stills, final Matt review'))
        events=self.runs.event_log.read(self.proposal.run_id)
        self.assertEqual(len(events),3)
        paid=next(e for e in events if e.event_type=='synthetic_payment_recorded')
        self.assertEqual(paid.payload['payment_status'],'simulated_paid')
        self.assertFalse(paid.payload['financial_authorisation'])
        self.assertIsNone(paid.payload['stripe_transaction'])
        with self.assertRaises(ValueError):
            self.service.enrol(self.proposal,authorisation_reference='another',scope_instruction='Different scope')

    def test_real_or_unclassified_entity_cannot_enrol(self):
        with self.assertRaises(PermissionError):self.service.enrol(self.proposal,authorisation_reference='x',scope_instruction='x')
        self.classify(GENUINE_CLIENT)
        with self.assertRaises(PermissionError):self.service.enrol(self.proposal,authorisation_reference='x',scope_instruction='x')

    def test_final_asset_review_cannot_be_simulated_and_lineage_is_checked(self):
        self.classify()
        policy=self.service.enrol(self.proposal,authorisation_reference='user:source',scope_instruction='Two stills')
        state=WorkflowState(ASSETS,'safe-assets',[],status=WorkflowStatus.AWAITING_APPROVAL,approval_status='pending',
            workspace_id='safe',client_id='safe-client',entity_id='safe-entity',
            input_payload={'_synthetic_rehearsal':policy,'asset_versions':[{'asset_id':'1'},{'asset_id':'2'}]})
        self.runs.repository.save(state)
        with self.assertRaisesRegex(PermissionError,'not descended'):self.service.review(state)
        state.input_payload['_lineage']={'parent_run_id':self.proposal.run_id}
        self.runs.repository.save(state)
        with self.assertRaisesRegex(PermissionError,'Final generated-asset approval'):self.service.review(state)

    def test_two_still_selection_excludes_video_and_keeps_full_creative_bible(self):
        contract=planning_contract();before=deepcopy(contract['approved_creative_bible'])
        contract['production_selection']={'maximum_assets':2,'allowed_capabilities':['image_generation'],
            'brand_name':'SAFE','cta':'Discover wholesale'}
        result=CampaignProductionPlanningWorker()(contract)
        self.assertEqual(len(result['production_tasks']),2)
        self.assertTrue(all(t['required_capability']=='image_generation' for t in result['production_tasks']))
        self.assertEqual(contract['approved_creative_bible'],before)
        self.assertTrue(production_planning_quality_gate(result)['passed'])
        self.assertIn('SAFE branding',result['channel_asset_specifications'][0]['creative_direction']['production_notes'])

    def test_account_model_retains_approved_mechanism_without_inventing_profit(self):
        intelligence={'mechanism':'incremental_accounts_year_one','inputs':[
            {'input_id':'annual_account_revenue','value':22000,'source_ids':['approved-fictional-proposal'],'status':'assumption'}],
            'scenario_assumptions':[{'name':name,'additional_accounts':a,'year_one_ramp':r} for name,a,r in
                [('Conservative',8,.35),('Base',12,.45),('Upside',16,.55)]],
            'implementation_cost':{'status':'unavailable','value':None}}
        model=build_quantified_commercial_model(intelligence)
        self.assertEqual([s['incremental_annual_revenue'] for s in model['scenarios']],[61600,118800,193600])
        self.assertTrue(all(s['incremental_annual_contribution'] is None for s in model['scenarios']))
        self.assertIsNone(model['estimated_current_annual_revenue'])
        self.assertTrue(all(commercial_model_quality_checks(model).values()))

class AutonomousAssetNotificationTests(unittest.TestCase):
    def test_final_folder_notification_is_sent_once_by_promised_worker(self):
        from runtime.tony_promised_work import TonyPromisedWorkWorker
        state=WorkflowState(ASSETS,'safe-assets',[],status=WorkflowStatus.AWAITING_APPROVAL,
            approval_status='pending',workspace_id='safe',client_id='safe-client',entity_id='safe-entity',
            input_payload={'_promised_work':{'commitment_id':'two-stills'},'_synthetic_rehearsal':{'policy_event_id':'verified'},
                'asset_versions':[{'asset_id':'one'},{'asset_id':'two'}]})
        class Backend:
            def list_states(self):return (state,)
            def progress_synthetic_rehearsal(self,s):return s
            def deliver_internal_review(self,s,recipient):
                return {'kind':'asset_review_folder','delivered':True,'review_link':'https://drive.google.com/drive/folders/verified',
                    'telegram_notification':'Two finished stills are ready for your review. Exact folder: https://drive.google.com/drive/folders/verified'}
            def begin_promised_delivery(self,s,delivery_key,kind):
                s.promised_work_delivery={'delivery_key':delivery_key,'kind':kind,'status':'attempting'};return s
            def finish_promised_delivery(self,s,delivery_key,evidence):
                s.promised_work_delivery={'delivery_key':delivery_key,'kind':'gate_ready','status':'delivered','evidence':evidence};return s
        sent=[]
        worker=TonyPromisedWorkWorker(Backend(),lambda message:sent.append(message) or {'message_id':'actual-test-provider-receipt'})
        worker.run_once();worker.run_once()
        self.assertEqual(len(sent),1)
        self.assertIn('https://drive.google.com/drive/folders/verified',sent[0])
        self.assertEqual(state.approval_status,'pending')

class AssetFolderReadbackTests(unittest.TestCase):
    def test_folder_parents_dimensions_and_checksum_are_verified_before_ready(self):
        from runtime.tony_workflow_commands import FileWorkflowCommandBackend
        with tempfile.TemporaryDirectory() as tmp:
            versions=[{'asset_version_id':f'asset-{i}-v1','drive_uri':f'https://drive.google.com/file/d/file-{i}/view',
                'file_checksum':str(i)*64,'approval_status':'pending','human_review_required':True} for i in (1,2)]
            state=WorkflowState(ASSETS,'safe-assets',[],workspace_id='safe',client_id='safe-client',entity_id='safe-entity',
                input_payload={'asset_versions':versions,'asset_review_folder_id':'safe-folder'})
            data={'safe-folder':{'id':'safe-folder','mimeType':'application/vnd.google-apps.folder',
                'webViewLink':'https://drive.google.com/drive/folders/safe-folder'}}
            for i in (1,2):data[f'file-{i}']={'id':f'file-{i}','mimeType':'image/png','parents':['safe-folder'],
                'appProperties':{'narratiiveChecksum':str(i)*64},'imageMediaMetadata':{'width':2048,'height':2048}}
            backend=FileWorkflowCommandBackend(tmp,dispatchers={'Google Drive':lambda request:{'verified':True,'metadata':data[request['target']['file_id']]}})
            audit=[]
            runtime=SimpleNamespace(_synthetic_rehearsal_service=lambda:SimpleNamespace(policy=lambda s:None),
                runs=SimpleNamespace(record_external_action=lambda *a,**kw:audit.append(kw)))
            ready=backend._asset_review_folder(runtime,state)
            self.assertEqual(ready['kind'],'asset_review_folder')
            self.assertIn(data['safe-folder']['webViewLink'],ready['telegram_notification'])
            self.assertEqual(len(audit),1)
            data['file-2']['parents']=['another-folder']
            with self.assertRaisesRegex(ValueError,'read-back'):backend._asset_review_folder(runtime,state)
            self.assertEqual(len(audit),1)

class SyntheticGateIdentityTests(SyntheticRehearsalTests):
    def test_internal_gate_records_simulation_not_a_founder_approval(self):
        from runtime.models import StageStatus
        self.classify()
        reference=self.service.enrol(self.proposal,authorisation_reference='user:source',scope_instruction='Bounded rehearsal')
        artifact=ArtifactRef('safe-thesis','workflow_step_output','unused','b'*64)
        state=WorkflowState('strategic_synthesis_to_strategy_thesis','safe-thesis-run',
            [StageRecord('thesis','specialist',status=StageStatus.COMPLETED,output_artifacts=[artifact])],
            status=WorkflowStatus.AWAITING_APPROVAL,approval_status='pending',approval_required=True,
            workspace_id='safe',client_id='safe-client',entity_id='safe-entity',
            input_payload={'_synthetic_rehearsal':reference,'_lineage':{'parent_run_id':self.proposal.run_id}})
        self.runs.repository.save(state)
        self.runtime.coordinator=SimpleNamespace(approve=lambda run_id,**kw:self.runs.approve(run_id,**kw))
        changed=self.service.review(state)
        approval=changed.approval_history[-1]
        self.assertEqual(approval['approval_kind'],'synthetic_rehearsal')
        self.assertFalse(approval['human_approval'])
        self.assertNotIn('Matt',approval['approver'])
        self.assertEqual(approval['approval_binding']['artifact_checksum'],artifact.checksum)
