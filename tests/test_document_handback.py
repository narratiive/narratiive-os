import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from runtime.document_handback import DocumentHandbackService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.native_business_adapters import GmailDispatcher, GoogleOAuthConfig
from tests.test_workflow_manual_recovery import _approval


class DocumentHandbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.runtime=build_tony_workflow_runtime(self.tmp.name,workspace_id='safe-ws',client_id='safe-client',environ={},dispatchers={})
        definition=self.runtime.coordinator.registry.resolve('growth_blueprint_deliverable_production')
        inputs={key:{'fixture':'Not real client strategy'} for key in definition.stages[0].required_inputs}
        inputs.update(blueprint_identity={'artifact_id':'fixture-strategy','version':1,'checksum':'a'*64},
            client_context={'name':'SAFE handback fixture'},
            evidence_lineage=[{'claim':'Synthetic fixture only, not a real client fact.','classification':kind,'source_refs':['fixture']}
                for kind in ('fact','interpretation','hypothesis','fact','interpretation')])
        self.runtime.enqueue(definition.workflow_id,'safe-handback',inputs,entity_id='safe-client',correlation_id='safe-handback')
        self.runtime.advance('safe-handback',ClientLifecycleRecord(client_id='safe-client',client_name='SAFE handback fixture',stage=ClientLifecycleStage.RESEARCH,owner='Tony',next_action='Fixture only'))
        self.state=self.runtime.runs.load_run('safe-handback')
        self.output={key:{'fixture':'Externally supplied test content; not automated quality acceptance'} for key in self.state.stages[0].expected_outputs}
        self.inputs={'workspace_id':'safe-ws','client_id':'safe-client','producing_specialist':'TEST external fixture producer','version':'v1','title':'SAFE Fieldwork handback fixture','output':self.output,
            'files':[{'output_field':field,'filename':name,'content_base64':base64.b64encode(data).decode()}
                for field,name,data in [('review_pdf','fixture.pdf',b'%PDF-1.7\nfixture\n%%EOF'),('editable_pptx','fixture.pptx',b'PK\x03\x04fixture')]]}

    def test_candidate_idempotency_exact_human_gate_and_draft_without_send(self):
        receipt={'verified':True,'sent':False,'draft_id':'test-only-draft'}
        gmail=Mock(return_value=receipt);service=DocumentHandbackService(self.runtime,{'Gmail':gmail})
        before=copy.deepcopy(self.state.approval_history)
        record=service.register(self.state,self.inputs,'test-authorised-human')
        self.assertEqual(service.register(self.state,self.inputs,'test-authorised-human'),record)
        self.assertEqual(self.runtime.runs.load_run(self.state.run_id).approval_history,before)
        with self.assertRaisesRegex(ValueError,'human manual recovery approval'): service.draft(self.state,record['manual_recovery']['recovery_id'])
        recovery=record['manual_recovery']
        self.runtime.recover_with_approved_artifact(self.state.run_id,**recovery,approver='test-human',rationale='Isolated fixture approval',approval_evidence=_approval('Recover this exact SAFE handback fixture after manual review.'))
        result=service.draft(self.state,recovery['recovery_id'])
        self.assertFalse(result['sent']);self.assertFalse(result['send_authorised'])
        self.assertEqual(gmail.call_args.args[0]['operation'],'create_draft')
        data=json.loads(Path(record['artifact']['location']).read_text())
        self.assertFalse(data['external_document_provenance']['automated_completion'])

    def test_scope_stage_output_and_approval_tampering_fail_closed(self):
        service=DocumentHandbackService(self.runtime,{})
        wrong=copy.deepcopy(self.inputs);wrong['client_id']='another-client'
        with self.assertRaisesRegex(ValueError,'binding'):service.register(self.state,wrong,'human')
        wrong=copy.deepcopy(self.inputs);wrong['output']['approval_status']='approved'
        with self.assertRaisesRegex(ValueError,'upstream inputs'):service.register(self.state,wrong,'human')
        wrong=copy.deepcopy(self.inputs);wrong['files']=wrong['files'][:1]
        with self.assertRaisesRegex(ValueError,'editable PPTX'):service.register(self.state,wrong,'human')
        self.assertEqual(self.runtime.runs.load_run(self.state.run_id).approval_status,'not_required')

    def test_gmail_draft_is_read_back_and_never_calls_send(self):
        gmail=GmailDispatcher(GoogleOAuthConfig(access_token='test-only'))
        stored={};calls=[]
        def api(url,**kw):
            calls.append(url)
            if '?q=' in url:return {'drafts':[]}
            if kw.get('method')=='POST':stored.update(kw['body']['message']);return {'id':'draft1'}
            return {'id':'draft1','message':dict(stored,id='message1')}
        gmail.client.call=api
        result=gmail({'execution_mode':'approved_write','approval_granted':True,'operation':'create_draft','idempotency_key':'fixture-draft',
            'payload':{'recipient_email':'hello@narratiive.com','subject':'TEST fixture','body':'Internal review only.','attachments':[{'filename':'test.pdf','mime_type':'application/pdf','content_base64':base64.b64encode(b'%PDF fixture').decode()}]}})
        self.assertFalse(result['sent']);self.assertTrue(result['verified'])
        self.assertTrue(result['attachment_checksums']);self.assertFalse(any('/send' in url for url in calls))

    def test_embedded_identity_conflicts_are_rejected(self):
        service=DocumentHandbackService(self.runtime,{})
        for key in ('workspace_id','client_id','run_id'):
            inputs=copy.deepcopy(self.inputs);inputs['output']['presentation_specification'][key]='another-engagement'
            with self.assertRaisesRegex(ValueError,'contradicts'):service.register(self.state,inputs,'test-human')

    def test_real_json_client_accepts_supported_pdf_size_and_rejects_extra_recipient_headers(self):
        from email.parser import BytesParser
        from email import policy
        from tests.test_native_business_adapters import Response
        for extra in (None,'Bcc','Cc','To'):
            stored={};calls=[]
            def opener(req,timeout):
                calls.append(req.full_url)
                if '?q=' in req.full_url:return Response({'drafts':[]})
                if req.method=='POST':
                    stored.update(json.loads(req.data)['message']);return Response({'id':'draft1'})
                raw=base64.urlsafe_b64decode(stored['raw']+'='*(-len(stored['raw'])%4))
                if extra:
                    raw=extra.encode()+b': unexpected@example.invalid\n'+raw
                return Response({'id':'draft1','message':{'raw':base64.urlsafe_b64encode(raw).decode(),'id':'msg1'}})
            gmail=GmailDispatcher(GoogleOAuthConfig(access_token='test-only'),opener=opener)
            contract={'execution_mode':'approved_write','approval_granted':True,'operation':'create_draft','idempotency_key':'large-test',
                'payload':{'recipient_email':'hello@narratiive.com','subject':'TEST','body':'Internal only',
                    'attachments':[{'filename':'fixture.pdf','mime_type':'application/pdf','content_base64':base64.b64encode(b'%PDF-'+b'x'*(999_995 if extra else 4_999_995)).decode()}]}}
            if extra:
                from runtime.native_business_adapters import BusinessAdapterError
                with self.assertRaisesRegex(BusinessAdapterError,'readback_mismatch'):gmail(contract)
            else:self.assertTrue(gmail(contract)['verified'])
            self.assertFalse(any('/send' in url for url in calls))

    def test_client_status_distinguishes_candidate_exact_approval_and_unsent_draft(self):
        from runtime.client_visibility import client_engagements,client_summary
        service=DocumentHandbackService(self.runtime,{'Gmail':Mock(return_value={'verified':True,'sent':False,'draft_id':'test-only'})})
        record=service.register(self.state,self.inputs,'test-human')
        def summary():
            state=self.runtime.runs.load_run(self.state.run_id)
            row=client_engagements([state])[0][1]
            return client_summary(state,row,None)
        self.assertIn('await exact manual review',summary())
        recovery=record['manual_recovery']
        self.runtime.recover_with_approved_artifact(self.state.run_id,**recovery,approver='test-human',rationale='Fixture',approval_evidence=_approval('Recover this exact SAFE fixture.'))
        self.assertIn('request internal draft preparation',summary())
        service.draft(self.state,recovery['recovery_id'])
        self.assertIn('Gmail draft is verified unsent',summary())
        self.assertIn('separate authorisation',summary())
