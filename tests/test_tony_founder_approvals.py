"""Synthetic Loom Loft acceptance without Telegram or provider network calls."""
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from openclaw.telegram_inbound import TelegramInboundConfig, TelegramInboundService
from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.tony_internal_review_delivery import workflow_approval_token
from runtime.tony_promised_work import TonyPromisedWorkWorker
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_tony_workflow_commands import FallbackCommands, blueprint_output, lifecycle
from tests.test_workflow_quality import discovery_output


class FounderApprovalTests(unittest.TestCase):
    instruction = "Loom Loft is approved for Discovery"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dispatchers = {"Claude": lambda contract: discovery_output() if contract['target']['workflow_context']['workflow_id'] == 'blueprint_lite_to_discovery_preparation' else blueprint_output()}
        self.runtime = build_tony_workflow_runtime(self.root, workspace_id='synthetic', client_id='safe-client', dispatchers=self.dispatchers, environ={})
        self.backend = FileWorkflowCommandBackend(self.root, workspace_id='synthetic', dispatchers=self.dispatchers, environ={})
        self.service = TonyWorkflowCommandService(FallbackCommands(), self.backend)
        self.create_gate('synthetic-loom')

    def create_gate(self, run_id):
        self.runtime.enqueue('growth_diagnostic_to_blueprint_lite', run_id, {'company': 'Loom Loft', 'diagnostic_input_package': {'source': 'synthetic fixture', 'overall_score': 40}}, entity_id='synthetic-loom', correlation_id=run_id)
        self.runtime.advance(run_id, lifecycle('safe-client'))

    def approve(self):
        return self.service.approve_discovery(self.instruction, principal_id='telegram:synthetic-founder')

    def test_unique_gate_records_bound_decision_and_queues_only_discovery(self):
        result = self.approve()
        self.assertEqual(result.status, 'healthy')
        source = self.runtime.runs.load_run('synthetic-loom')
        self.assertEqual(len(source.approval_history), 1)
        binding = source.approval_history[0]['approval_binding']
        self.assertEqual(binding['human_decision']['human_instruction'], self.instruction)
        self.assertTrue(binding['artifact_checksum'])
        states = self.backend.list_states()
        self.assertEqual(len(states), 2)
        target = next(state for state in states if state.run_id != source.run_id)
        self.assertEqual(target.workflow_id, 'blueprint_lite_to_discovery_preparation')
        self.assertEqual(target.status.value, 'active')
        self.assertIn('_promised_work', target.input_payload)
        self.assertFalse(target.external_action_taken)
        self.assertNotIn(source.run_id, result.message)

    def test_ambiguous_and_missing_gate_clarify_without_mutation(self):
        self.create_gate('synthetic-second')
        result = self.approve()
        self.assertEqual(result.message.count('?'), 1)
        self.assertTrue(all(not state.approval_history for state in self.backend.list_states()))
        with patch.object(self.backend, 'list_states', return_value=()):
            self.assertEqual(self.approve().message.count('?'), 1)

    def test_duplicate_does_not_repeat_approval_or_bypass_next_gate(self):
        self.approve()
        repeat = self.approve()
        self.assertIn('already recorded', repeat.message)
        self.assertEqual(len(self.runtime.runs.load_run('synthetic-loom').approval_history), 1)
        messages = []
        worker = TonyPromisedWorkWorker(self.backend, lambda text: messages.append(text) or {'message_id': 'synthetic-receipt'})
        target = worker.run_once()
        self.assertEqual(target.status.value, 'awaiting_approval')
        self.assertIn('couldn’t verify delivery', messages[0])
        self.assertIsNone(worker.run_once())
        self.approve()
        self.assertEqual(len(self.backend.list_states()), 2)
        self.assertEqual(self.runtime.runs.load_run(target.run_id).approval_status, 'pending')

    def test_stale_snapshot_rejected_at_persistence_boundary(self):
        stale = self.runtime.runs.load_run('synthetic-loom')
        token = workflow_approval_token(stale)
        current = self.runtime.runs.load_run('synthetic-loom')
        stage = next(stage for stage in current.stages if stage.output_artifacts)
        stage.output_artifacts[-1] = replace(stage.output_artifacts[-1], checksum='new-synthetic-version')
        self.runtime.runs.repository.save(current)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.backend.approve(stale, approver='telegram:synthetic-founder', rationale=self.instruction, approval_token=token)
        self.assertEqual(self.runtime.runs.load_run('synthetic-loom').approval_history, [])

    def test_missing_identity_and_conditional_intent_cannot_approve(self):
        self.assertEqual(self.service.approve_discovery(self.instruction, principal_id='').status, 'error')
        self.assertFalse(self.service.is_discovery_approval(self.instruction + ' if the research checks out'))
        self.assertEqual(self.runtime.runs.load_run('synthetic-loom').approval_history, [])

    def test_commission_failure_acknowledges_only_persisted_approval(self):
        with patch.object(self.backend, 'commission', side_effect=ValueError('synthetic failure')):
            result = self.approve()
        self.assertEqual(result.status, 'blocked')
        self.assertIn('approval is recorded', result.message)
        self.assertNotIn('is queued', result.message)
        self.assertEqual(len(self.backend.list_states()), 1)
        recovered = self.approve()
        self.assertTrue(recovered.data['commissioned'])
        self.assertEqual(len(self.runtime.runs.load_run('synthetic-loom').approval_history), 1)

    def test_ingress_checks_principal_before_bypassing_model(self):
        base = Mock(bridge_token='synthetic-bridge-token')
        gateway = Mock()
        app = LeadAwareTonyApplication(base, Mock(), agent_gateway=gateway, workflow_command_service=self.service, authorised_principal_id='telegram:synthetic-founder')
        for principal, expected in [('telegram:other', False), ('telegram:synthetic-founder', True)]:
            body = json.dumps({'text': self.instruction, 'principal_id': principal}).encode()
            env = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/telegram/inbound', 'HTTP_AUTHORIZATION': 'Bearer synthetic-bridge-token', 'CONTENT_LENGTH': str(len(body)), 'wsgi.input': io.BytesIO(body)}
            result = json.loads(b''.join(app(env, lambda *args: None)))
            self.assertEqual(result['ok'], expected)
        gateway.converse.assert_not_called()

    def test_poller_routes_exact_instruction_to_authenticated_bridge(self):
        gateway = Mock()
        poller = TelegramInboundService(TelegramInboundConfig('synthetic', 'synthetic-founder'), agent_gateway=gateway)
        with patch.object(poller, '_execute_legacy_command', return_value='Recorded') as execute:
            self.assertEqual(poller._execute_tony(self.instruction), 'Recorded')
            execute.assert_called_once_with(self.instruction)
        gateway.converse.assert_not_called()

    def test_other_workspace_gate_is_not_resolved_or_changed(self):
        other = build_tony_workflow_runtime(self.root, workspace_id='other-synthetic', client_id='safe-client', dispatchers=self.dispatchers, environ={})
        other.enqueue('growth_diagnostic_to_blueprint_lite', 'other-run', {'company': 'Loom Loft', 'diagnostic_input_package': {'source': 'synthetic'}}, entity_id='other', correlation_id='other')
        other.advance('other-run', lifecycle('safe-client'))
        self.assertEqual(self.approve().status, 'healthy')
        self.assertEqual(other.runs.load_run('other-run').approval_status, 'pending')
