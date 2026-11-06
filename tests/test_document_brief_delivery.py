"""Regression coverage for Telegram message 1184 / n8n execution 3600."""
import re
import unittest
from types import SimpleNamespace

from runtime.document_handback import FIELDWORK_SPEC, format_document_brief
from runtime.tony_workflow_commands import TonyWorkflowCommandService

RUN = 'origin-coffee-fictional-e2e-20261103'


def state(run_id=RUN, **changes):
    stage = SimpleNamespace(stage_id='prepare_blueprint_lite', side_effect_classification='preparation', expected_outputs=('blueprint_lite',))
    values = dict(run_id=run_id, entity_id=RUN, client_id=RUN, workspace_id='narratiive',
                  workflow_id='growth_diagnostic_to_blueprint_lite', input_payload={'company':'TEST Origin'},
                  current_stage_id=stage.stage_id, stages=[stage], stage=lambda _: stage,
                  status=SimpleNamespace(value='blocked'), approval_status='not_required')
    values.update(changes)
    return SimpleNamespace(**values)


class DocumentBriefDeliveryTests(unittest.TestCase):
    def test_exact_origin_run_precedes_shared_engagement_identity(self):
        original = state()
        child = state(RUN + '--revision-3ce5969bb249-blueprint_lite_to_discovery_preparation')
        self.assertIs(TonyWorkflowCommandService._resolve((child, original), RUN), original)
        # A genuine duplicate canonical identity remains ambiguous; never pick silently.
        with self.assertRaises(LookupError):
            TonyWorkflowCommandService._resolve((original, state()), RUN)

    def test_execution_3600_legacy_markdown_dynamic_text_is_safe(self):
        # The exact failing response contained these unescaped underscore identifiers.
        failing = 'Reference is ambiguous; use a run ID: ' + RUN + ', ' + RUN + '--revision-3ce5969bb249-blueprint_lite_to_discovery_preparation'
        brief = {'client_name': failing + ' [source]*`\\', 'deadline':'Matt_to_agree',
                 'source_register':{'entries':[{'location':'https://example.test/source_one?q=[test]'}]}}
        reply = format_document_brief(state(), brief)
        self.assertIn(r'blueprint\_lite\_to\_discovery\_preparation', reply)
        # Consume every escape pair. No remaining character can open a Markdown entity.
        self.assertNotRegex(re.sub(r'\\.', '', reply), r'[_*`\[]')
        self.assertLessEqual(len(reply), 3400)
        self.assertFalse(reply.endswith('\\'))
        self.assertIn(FIELDWORK_SPEC, reply)

    def test_brief_is_readable_honest_and_preserves_required_next_action(self):
        original = state(input_payload={'diagnostic_input_package':{'diagnostic':{
            'challenge':'Test growth opportunity, not validated.',
            'recommended_actions':['Validate audience','Assess channel economics'],
            'raw_answers':{'unknowns':['Retention','Leadership priority'], 'source_urls':['https://www.origincoffee.co.uk/']}}}})
        before = repr(original.input_payload)
        reply = format_document_brief(original, {'client_name':'TEST / FICTIONAL Origin Coffee','deadline':'Not supplied; agree with Matt.'})
        for phrase in ('Exact engagement:', 'approval: not', 'Recorded hypothesis', 'Recommended Fieldwork focus',
                       'Fieldwork v7 specification', 'Recorded evidence reference', 'No verified production',
                       'This run cannot adopt', 'No file created'):
            self.assertIn(phrase, reply)
        self.assertEqual(repr(original.input_payload), before)
        self.assertNotIn('{"', reply)


if __name__ == '__main__':
    unittest.main()
