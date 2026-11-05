from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from runtime.fieldwork_proposal import TEMPLATE
from runtime.fieldwork_workflow import email_draft
from runtime.human_review_artifacts import HumanReviewArtifactStore, HumanReviewPresentationService
from runtime.models import ArtifactRef
from runtime.workflow_quality import growth_sprint_proposal_quality_gate
from tests.test_human_review_artifacts import state
from tests.test_workflow_quality import proposal_output


class FieldworkWorkflowQualityTests(unittest.TestCase):
    def test_legacy_or_incomplete_commercial_terms_cannot_pass(self):
        output = proposal_output()
        self.assertTrue(growth_sprint_proposal_quality_gate(output)['passed'])
        for edit in (
            lambda d: d.pop('fieldwork_proposal'),
            lambda d: d['fieldwork_proposal']['proposed_fee'].update(approved=True),
            lambda d: d['commercial_proposal_inputs'].update(timeline='Four weeks'),
            lambda d: d['commercial_proposal_inputs']['proposed_fee'].update(amount='1'),
            lambda d: d.update(draft_client_communication='A Growth Sprint proposal'),
        ):
            candidate = deepcopy(output)
            edit(candidate)
            self.assertFalse(growth_sprint_proposal_quality_gate(candidate)['passed'])

    def test_email_identity_changes_with_pdf_or_source(self):
        output = proposal_output()
        a = email_draft(output, 'a'*64, source_checksum='1'*64)
        b = email_draft(output, 'b'*64, source_checksum='1'*64)
        self.assertNotEqual(a['draft_sha256'], b['draft_sha256'])
        self.assertFalse(a['send_authorised'])
        self.assertIsNone(a['recipient_email'])

    @unittest.skipUnless(Path('/System/Library/Fonts/Supplemental/Baskerville.ttc').is_file(), 'Exact approved Mac fonts required')
    def test_review_stores_two_page_pdf_and_checksum_bound_email_without_approval(self):
        output = proposal_output()
        raw = json.dumps(output,sort_keys=True,separators=(',',':')).encode()
        source = ArtifactRef(artifact_id='safe-source',artifact_type='workflow_step_output',
            location='unused',checksum=hashlib.sha256(raw).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            review = HumanReviewPresentationService(HumanReviewArtifactStore(tmp)).produce(
                state=state('discovery_evidence_to_growth_sprint_proposal'),source=source,output=output)
            self.assertEqual(review.page_count,2)
            self.assertEqual(review.renderer_id,'narratiive-fieldwork-proposal')
            folder = Path(review.location).parent
            draft = json.loads((folder/'client-email-draft.json').read_text())
            self.assertEqual(draft['pdf_sha256'],hashlib.sha256(Path(review.location).read_bytes()).hexdigest())
            self.assertFalse(draft['proposed_fee']['approved'])
            self.assertFalse(draft['send_authorised'])
            # A caller cannot render changed copy against the old immutable source.
            changed = deepcopy(output)
            changed['fieldwork_proposal']['client_id']='another-client'
            with self.assertRaises(ValueError):
                HumanReviewPresentationService(HumanReviewArtifactStore(tmp)).produce(
                    state=state('discovery_evidence_to_growth_sprint_proposal'),source=source,output=changed)

class FieldworkRevisionTests(unittest.TestCase):
    def test_revision_retains_prior_artifact_and_does_not_approve_fee(self):
        from runtime.tony_workflow_runtime import build_tony_workflow_runtime
        from tests.test_workflow_action_preview import lifecycle
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(tmp, workspace_id='narratiive', client_id='safe-client',
                dispatchers={'Claude': lambda contract: proposal_output()}, environ={})
            run_id = 'safe-fieldwork-revision'
            runtime.enqueue('discovery_evidence_to_growth_sprint_proposal',run_id,
                {'discovery_evidence': {'notes':'Explicitly fictional preparation, no real discovery call.',
                  'sources':[{'source_id':'safe-notes','source_type':'notes','location':'synthetic:test'}]},
                 'blueprint_lite':'Synthetic approved Groundwork evidence.',
                 'commercial_context':{'company':'SAFE Review Company'}},
                entity_id='safe-client',correlation_id='safe-test')
            runtime.advance(run_id,lifecycle('safe-client'))
            prior = runtime.runs.load_run(run_id)
            old = prior.stages[0].output_artifacts[-1]
            original = Path(old.location).read_bytes()
            supplied = proposal_output()['fieldwork_proposal']
            supplied['proposed_fee']['amount']='8400'
            wrong = deepcopy(supplied)
            wrong['client_id']='another-client'
            with self.assertRaises(ValueError):
                runtime.reject_for_revision(run_id,reviewer='authorised-test-human',rationale='Reject cross-client input',
                    fieldwork_revision_inputs=wrong)
            self.assertEqual(runtime.runs.load_run(run_id).approval_status,'pending')
            runtime.reject_for_revision(run_id,reviewer='authorised-test-human',rationale='Request exact new candidate',
                fieldwork_revision_inputs=supplied)
            runtime.advance(run_id,lifecycle('safe-client'))
            revised = runtime.runs.load_run(run_id)
            self.assertEqual(revised.status.value,'awaiting_approval')
            self.assertEqual(revised.approval_status,'pending')
            self.assertEqual(len(revised.stages[0].output_artifacts),2)
            self.assertEqual(Path(old.location).read_bytes(),original)
            new = json.loads(Path(revised.stages[0].output_artifacts[-1].location).read_text())
            self.assertEqual(new['fieldwork_proposal'],supplied)
            self.assertEqual(new['commercial_proposal_inputs']['proposed_fee']['amount'],'8400')
            self.assertFalse(new['fieldwork_proposal']['proposed_fee']['approved'])
            self.assertEqual(revised.approval_history[-1]['decision'],'request_revision')
