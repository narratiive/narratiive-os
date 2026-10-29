from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openclaw.mission_control_web import HTML, MissionControlWebApplication
from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.mission_control_operator import OperatorMissionControlProjector
from runtime.mission_control_sources import read_marketing, read_n8n_executions, read_operator_leads
from runtime.models import ArtifactRef, StageRecord, StageStatus, WorkflowState, WorkflowStatus


class OperatingViewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.projector = OperatorMissionControlProjector(workflow_root=self.root, workflow_workspace_id='agency')

    def tearDown(self):
        self.tmp.cleanup()

    def completed(self, client='synthetic-company'):
        scope = hashlib.sha256(f'agency:{client}'.encode()).hexdigest()[:24]
        directory = self.root / scope
        (directory / 'artifacts').mkdir(parents=True)
        (directory / 'events').mkdir()
        artifact_path = directory / 'artifacts/output.json'
        artifact_path.write_text('{"synthetic":true}')
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        artifact = ArtifactRef('output-v1', 'workflow_step_output', str(artifact_path), checksum)
        stage = StageRecord('research', 'Research Analyst', status=StageStatus.COMPLETED, output_artifacts=[artifact], quality_result={'passed': True}, completed_at='2026-10-24T10:00:00Z')
        state = WorkflowState('strategy_thesis_to_growth_blueprint', 'shared-run', [stage], workspace_id='agency', client_id=client, entity_id=client, status=WorkflowStatus.COMPLETE, approval_required=True, approval_status='approved')
        approval = {'approver':'test-human','rationale':'Synthetic approval', 'approved_at':'2026-10-24T10:10:00Z', 'approval_binding':{'artifact_id':artifact.artifact_id,'artifact_checksum':checksum}}
        state.approval_history.append(approval)
        events = [self.event(state, 'stage.completed', {'stage_id':'research','output_artifact_ids':['output-v1']}), self.event(state, 'approval.granted', approval)]
        path = directory / 'events/shared-run.jsonl'
        self.write_events(path, events)
        return state, path

    @staticmethod
    def event(state, kind, payload):
        return {'event_id':kind, 'run_id':state.run_id, 'event_type':kind, 'payload':payload, 'occurred_at':'2026-10-24T10:10:00Z','workspace_id':state.workspace_id}

    @staticmethod
    def write_events(path, events):
        path.write_text(''.join(json.dumps(event)+'\n' for event in events))

    def item(self, state):
        return self.projector.project(states=[state], leads=[])['opportunities'][0]

    def test_complete_requires_checksummed_output_quality_completion_event_and_exact_approval(self):
        state, _ = self.completed()
        self.assertTrue(self.item(state)['runs'][0]['completion_verified'])
        state.approval_history[-1]['approval_binding']['artifact_checksum'] = 'wrong-version'
        item = self.item(state)
        self.assertFalse(item['runs'][0]['completion_verified'])
        self.assertEqual(item['attention_state'], 'unverified')
        self.assertEqual(item['artefacts'][0]['approval_status'], 'not_recorded')

    def test_tampered_and_missing_outputs_cannot_verify_completion(self):
        state, _ = self.completed()
        output = Path(state.stages[0].output_artifacts[0].location)
        output.write_text('tampered')
        self.assertFalse(self.item(state)['runs'][0]['completion_verified'])
        output.unlink()
        self.assertFalse(self.item(state)['runs'][0]['completion_verified'])

    def test_stage_order_does_not_imply_earlier_work_completed(self):
        state, _ = self.completed()
        journey = self.item(state)['journey']
        self.assertTrue(all(x['state'] == 'unknown' for x in journey if x['id'] in {'lead','discovery','proposal'}))
        self.assertEqual(next(x for x in journey if x['id'] == 'delivery')['state'], 'complete')

    def test_missing_and_corrupt_events_remain_visible_blockers(self):
        state, path = self.completed()
        path.write_text('broken JSON')
        item = self.item(state)
        self.assertTrue(any('unreadable' in x for x in item['evidence_issues']))
        self.assertFalse(item['runs'][0]['completion_verified'])
        path.unlink()
        result = self.projector.project(states=[state], leads=[])
        self.assertTrue(result['operations']['blockers'])
        self.assertIsNone(result['opportunities'][0]['last_successful_activity_at'])

    def test_identical_run_id_in_another_client_does_not_hide_own_history(self):
        first, _ = self.completed('first')
        self.completed('second')
        self.assertEqual(len(self.item(first)['activity']), 2)

    def test_detail_retains_more_than_twelve_events_and_attempt_failures(self):
        state, path = self.completed()
        events = [self.event(state, 'stage.attempt_recorded', {'attempt':i, 'secret':'NEVER EXPOSE'}) for i in range(18)]
        self.write_events(path, events)
        item = self.item(state)
        self.assertEqual(len(item['activity']), 18)
        self.assertNotIn('NEVER EXPOSE', json.dumps(item))

    def test_foreign_run_events_are_not_accepted_as_completion_evidence(self):
        state, path = self.completed()
        events = [self.event(state, 'stage.completed', {'stage_id':'research','output_artifact_ids':['output-v1']})]
        events[0]['run_id'] = 'another-run'
        self.write_events(path, events)
        self.assertFalse(self.item(state)['runs'][0]['completion_verified'])

    def test_failed_quality_and_stale_artifact_completion_event_are_unverified(self):
        state, path = self.completed()
        state.stages[0].quality_result = {'passed':False}
        self.assertFalse(self.item(state)['runs'][0]['completion_verified'])
        state.stages[0].quality_result = {'passed':True}
        self.write_events(path, [self.event(state, 'stage.completed', {'stage_id':'research','output_artifact_ids':['old-version']})])
        self.assertFalse(self.item(state)['runs'][0]['completion_verified'])

    def test_n8n_read_is_metadata_only_and_never_changes_database(self):
        path = self.root/'n8n.sqlite'
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE execution_entity (id INTEGER, workflowId TEXT, status TEXT, startedAt TEXT, stoppedAt TEXT, retryOf TEXT, retrySuccessId TEXT, deletedAt TEXT)')
        db.execute("INSERT INTO execution_entity VALUES (1,'flow','error','start','stop',NULL,'2',NULL)")
        db.execute("INSERT INTO execution_entity VALUES (2,'flow','success','start','stop','1',NULL,NULL)")
        db.commit()
        db.close()
        before = path.read_bytes()
        result = read_n8n_executions({'TONY_DISPATCH_N8N_MODE':'local_sqlite','TONY_N8N_DATABASE_PATH':str(path)})
        self.assertEqual(result['state'], 'connected')
        self.assertEqual([x['status'] for x in result['executions']], ['success','error'])
        self.assertEqual(result['executions'][0]['retry_of'], '1')
        self.assertEqual(path.read_bytes(), before)

    def test_missing_n8n_and_unsupported_schema_are_explicit(self):
        self.assertEqual(read_n8n_executions({})['state'], 'not_connected')
        path = self.root/'n8n.sqlite'
        sqlite3.connect(path).close()
        result = read_n8n_executions({'TONY_DISPATCH_N8N_MODE':'local_sqlite','TONY_N8N_DATABASE_PATH':str(path)})
        self.assertEqual(result['state'], 'degraded')
        self.assertEqual(result['executions'], [])

    def test_marketing_missing_or_archived_source_does_not_invent_production(self):
        for env in ({}, {'NARRATIIVE_NOTION_MARKETING_DATA_SOURCE_ID':'2920c9cf-a8f2-8129-bfbf-000b9ca47fa8'}):
            result = read_marketing(env)
            self.assertEqual(result['state'], 'not_connected')
            self.assertEqual(result['items'], [])
            self.assertFalse(result['publication_enabled'])
            self.assertIsNone(result['metrics'])

    @patch('runtime.mission_control_sources.NotionLeadSource._query_page')
    def test_marketing_status_label_cannot_become_verified_publication(self, query):
        query.return_value = {'results':[{'id':'synthetic', 'properties':{'Title':{'title':[{'plain_text':'Synthetic draft'}]},'Status':{'select':{'name':'Published'}}}}]}
        result = read_marketing({'NARRATIIVE_NOTION_MARKETING_DATA_SOURCE_ID':'synthetic-source','NOTION_TOKEN':'DO_NOT_EXPOSE'})
        self.assertEqual(result['state'], 'connected')
        self.assertIn('Not verified', result['items'][0]['publication'])
        self.assertNotIn('DO_NOT_EXPOSE', json.dumps(result))

    @patch('runtime.mission_control_sources.NotionLeadSource._query_page')
    def test_marketing_partial_pagination_and_schema_fail_closed(self, query):
        env = {'NARRATIIVE_NOTION_MARKETING_DATA_SOURCE_ID':'synthetic-source','NOTION_TOKEN':'DO_NOT_EXPOSE'}
        for payload in ({'results':[], 'has_more':True}, {'results':[{'properties':{'Other':{}}}]}):
            query.return_value = payload
            result = read_marketing(env)
            self.assertEqual(result['state'], 'degraded')
            self.assertEqual(result['items'], [])
            self.assertNotIn('DO_NOT_EXPOSE', json.dumps(result))

    @patch('runtime.mission_control_sources.NotionLeadSource._query_page')
    def test_operator_notion_read_does_not_write_lead_cache(self, query):
        cache = FileInboundLeadStore(self.root/'leads.json')
        cache.replace([InboundLead('old','Synthetic old')])
        before = cache.path.read_bytes()
        query.return_value = {'results':[{'id':'new','properties':{'Contact':{'title':[{'plain_text':'Synthetic new'}]}}}]}
        leads = read_operator_leads({'NOTION_TOKEN':'secret'}, cache)
        self.assertEqual(leads[0].lead_id, 'new')
        self.assertEqual(cache.path.read_bytes(), before)

    def test_source_failure_returns_unavailable_without_private_exception(self):
        def failed():
            raise RuntimeError('credential SHOULD_NOT_LEAK')
        app = MissionControlWebApplication(failed, workflow_root=self.root)
        status = {}
        body = app.handle({'REMOTE_ADDR':'127.0.0.1','PATH_INFO':'/mission-control/api'},lambda value, headers:status.update(value=value))
        self.assertTrue(status['value'].startswith('503'))
        self.assertNotIn(b'SHOULD_NOT_LEAK', b''.join(body))

    def test_three_views_and_complete_history_are_present(self):
        for label in ('Business Pipeline','Operations Centre','Marketing Studio','Complete recorded activity history','Operational blocker register'):
            self.assertIn(label, HTML)
        self.assertNotIn('innerHTML=x.draft', HTML)


if __name__ == '__main__':
    unittest.main()
