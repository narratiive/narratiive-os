import unittest
from types import SimpleNamespace
from runtime.workflow_handoffs import build_next_workflow_inputs


class DirectorWorkflowHandoffTests(unittest.TestCase):
    def test_campaign_receives_exact_quality_accepted_story_and_parent_lineage(self):
        blueprint = {'client_facing_blueprint': {'pages': [{'headline': 'Exact approved story'}]}, 'editorial_trace': []}
        source = SimpleNamespace(workflow_id='growth_blueprint_deliverable_production', run_id='source-review',
            input_payload={'quality_accepted_growth_blueprint': blueprint}, stages=[], approval_history=[])
        result = build_next_workflow_inputs(source, {'review_pdf': 'internal-review.pdf'})
        self.assertEqual(result['growth_blueprint'], blueprint)
        self.assertEqual(result['_lineage']['parent_run_id'], 'source-review')
        self.assertNotIn('publication_authorised', result)
