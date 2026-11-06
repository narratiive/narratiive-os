"""Presentation only: exact Fieldwork evidence, complete copyable response."""
import copy
import re
import unittest
from runtime.document_handback import DocumentHandbackService, format_document_brief, FIELDWORK_SPEC
from tests.test_document_brief_delivery import state


def fieldwork():
    return state(run_id='exact-fieldwork-record', workflow_id='growth_blueprint_deliverable_production',
        status=type('Status', (), {'value':'complete'})(), approval_status='approved',
        approval_history=[{'approval_kind':'synthetic_rehearsal','human_approval':False}],
        input_payload={
            'company':'TEST Origin', 'blueprint_identity':{'artifact_id':'approved-strategy','checksum':'sha'},
            'diagnostic_input_package':{'diagnostic':{'challenge':'Obsolete subscription direction'}},
            'growth_opportunity':{'diagnosis':'Established hospitality operators need proof that switching is safe.'},
            'central_thesis':{'insight':'Prioritise established cafés and boutique hotels at natural switching moments.'},
            'source_register':{'entries':[{'source_id':'S1','location':'https://example.test/wholesale_one','classification':'public_source'},
                {'source_id':'P1','location':'/immutable/model.md','classification':'assumption'}]},
            'evidence_and_uncertainty':['Fictional rehearsal: no actual client discovery or financials.', 'Public-source verification failed.'],
            'assumption_control':{'missing_evidence':['Leadership priority unconfirmed','Pipeline and margins unknown']},
            'commercial_model':{'classification':'illustrative_scenario_model','scenarios':[{
                'additional_accounts':12, 'annual_account_revenue':22000,'year_one_ramp':0.45,'incremental_annual_revenue':118800}]},
            'evidence_lineage':[{'claim':'Recorded documentary account only','classification':'hypothesis','source_refs':['P1']}],
            'asset_review_folder_url':'https://drive.google.com/drive/folders/stills-only',
        })


class SpecialistBriefPresentationTests(unittest.TestCase):
    def test_complete_copyable_brief_uses_exact_approved_fieldwork_not_diagnostic(self):
        selected=fieldwork(); before=copy.deepcopy(selected.input_payload)
        result=DocumentHandbackService(None,{}).brief(selected)
        text=format_document_brief(selected,result)
        for phrase in ('Fieldwork presentation','Problem:','Tony recommends:','Copy to Claude:',
                       'Established hospitality','boutique hotels','£118800','not forecast/profit',
                       'v7.2','editable PPTX + matching PDF','source register','visual QA','Handback:',
                       'Matt next:','Leadership priority unconfirmed','completed run cannot adopt',FIELDWORK_SPEC):
            self.assertIn(phrase,text)
        self.assertNotIn('Obsolete subscription',text)
        self.assertNotIn(selected.run_id,text)
        self.assertNotIn('growth_blueprint',text)
        self.assertIn('not Matt/client approval',text)
        self.assertNotIn('stills-only',text)
        self.assertEqual(selected.input_payload,before)
        audit=result['specialist_audit']
        self.assertEqual(audit['requested_run_id'],selected.run_id)
        self.assertEqual(audit['source_register'],before['source_register'])
        self.assertEqual(audit['strategy']['assumption_control'],before['assumption_control'])
        self.assertEqual(audit['strategy_identity'],before['blueprint_identity'])
        self.assertIn('v7.2',audit['specification_sections'])
        self.assertNotRegex(re.sub(r'\\.', '', text),r'[_*`\[]')
        self.assertIn(r'wholesale\_one',text)
        self.assertLessEqual(len(text),3400)

    def test_missing_approval_or_evidence_is_explicit_without_selecting_another_run(self):
        selected=fieldwork();selected.approval_status='pending';selected.input_payload.pop('central_thesis')
        text=format_document_brief(selected,DocumentHandbackService(None,{}).brief(selected))
        self.assertIn('missing approved Fieldwork evidence',text)
        self.assertIn('strategic recommendation',text)
        self.assertIn('No run was substituted',text)

    def test_oversized_evidence_does_not_silently_truncate_the_copyable_brief(self):
        selected=fieldwork();selected.input_payload['assumption_control']['missing_evidence']=['A'*4000]
        text=format_document_brief(selected,DocumentHandbackService(None,{}).brief(selected))
        self.assertIn('exceeds one complete Telegram',text)
        self.assertIn('no evidence was truncated',text)
        self.assertNotIn('Copy to Claude',text)
