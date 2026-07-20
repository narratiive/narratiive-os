import unittest

from runtime.tony_orchestration import (
    FakeGatewayTransport,
    TonyCommand,
    TonyGatewayError,
    TonyOrchestrationAdapter,
)


class TonyOrchestrationTests(unittest.TestCase):
    def test_maps_actions_to_public_gateway_with_idempotency_and_correlation(self):
        transport = FakeGatewayTransport([
            {"ok": True, "command": "runs.get", "data": {"status": "awaiting_approval"}}
        ])
        adapter = TonyOrchestrationAdapter(transport)
        result = adapter.execute(
            TonyCommand(
                action="run.status",
                workspace_id="rave",
                client_id="rave-client",
                command_id="command-1",
                payload={"run_id": "rave-blueprint-1"},
            )
        )
        call = transport.calls[0]
        self.assertEqual(call["payload"]["command"], "runs.get")
        self.assertEqual(call["payload"]["workspace_id"], "rave")
        self.assertEqual(call["idempotency_key"], "command-1")
        self.assertEqual(call["correlation_id"], "tony-command-1")
        self.assertIn("awaiting_approval", result.message)

    def test_duplicate_commands_reuse_same_idempotency_key(self):
        transport = FakeGatewayTransport()
        adapter = TonyOrchestrationAdapter(transport)
        command = TonyCommand(
            action="run.list",
            workspace_id="rave",
            client_id="rave-client",
            command_id="duplicate-1",
        )
        adapter.execute(command)
        adapter.execute(command)
        self.assertEqual(
            [call["idempotency_key"] for call in transport.calls],
            ["duplicate-1", "duplicate-1"],
        )

    def test_rejects_cross_workspace_payload_before_transport(self):
        transport = FakeGatewayTransport()
        adapter = TonyOrchestrationAdapter(transport)
        with self.assertRaisesRegex(TonyGatewayError, "workspace_id"):
            adapter.execute(
                TonyCommand(
                    action="blueprint.generate",
                    workspace_id="rave",
                    client_id="rave-client",
                    command_id="cross-1",
                    payload={"request": {"workspace_id": "maeving"}},
                )
            )
        self.assertEqual(transport.calls, [])

    def test_approval_identity_and_rationale_are_preserved(self):
        transport = FakeGatewayTransport()
        adapter = TonyOrchestrationAdapter(transport)
        adapter.execute(
            TonyCommand(
                action="approve",
                workspace_id="rave",
                client_id="rave-client",
                command_id="approve-1",
                reviewer_id="matt",
                rationale="Founder review complete",
                payload={"run_id": "rave-blueprint-1"},
            )
        )
        payload = transport.calls[0]["payload"]
        self.assertEqual(payload["reviewer_id"], "matt")
        self.assertEqual(payload["rationale"], "Founder review complete")
        self.assertEqual(payload["command"], "approvals.approve")

    def test_export_uses_public_export_command(self):
        transport = FakeGatewayTransport([
            {
                "ok": True,
                "command": "blueprints.export",
                "data": {
                    "status": "completed",
                    "presentation_url": "https://docs.google.com/presentation/d/deck/edit",
                },
            }
        ])
        result = TonyOrchestrationAdapter(transport).execute(
            TonyCommand(
                action="blueprint.export",
                workspace_id="rave",
                client_id="rave-client",
                command_id="export-1",
                payload={"blueprint_id": "rave-growth-blueprint", "blueprint_version": 1},
            )
        )
        self.assertEqual(transport.calls[0]["payload"]["command"], "blueprints.export")
        self.assertIn("completed", result.message)

    def test_create_growth_blueprint_starts_then_dispatches_without_approval_bypass(self):
        transport = FakeGatewayTransport()
        adapter = TonyOrchestrationAdapter(transport)
        adapter.create_growth_blueprint(
            workspace_id="rave",
            client_id="rave-client",
            command_id="growth-1",
            run_id="rave-run-1",
            definition_path="workflows/growth-blueprint.json",
            available_inputs=["client_brief"],
        )
        commands = [call["payload"]["command"] for call in transport.calls]
        self.assertEqual(commands, ["runs.create", "stages.dispatch"])
        self.assertNotIn("approvals.approve", commands)
        self.assertNotIn("blueprints.export", commands)

    def test_gateway_errors_are_actionable_without_stack_traces(self):
        transport = FakeGatewayTransport([
            {
                "ok": False,
                "error": {
                    "code": "approval_required",
                    "message": "Human approval is required before export",
                    "retryable": False,
                },
            }
        ])
        with self.assertRaises(TonyGatewayError) as captured:
            TonyOrchestrationAdapter(transport).execute(
                TonyCommand(
                    action="blueprint.export",
                    workspace_id="rave",
                    client_id="rave-client",
                    command_id="blocked-1",
                )
            )
        self.assertEqual(captured.exception.code, "approval_required")
        self.assertNotIn("Traceback", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
