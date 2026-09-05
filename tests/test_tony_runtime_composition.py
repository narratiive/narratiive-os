from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw import tony_http_bridge, tony_live_bridge
from runtime import server
from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_workflow_commands import TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from runtime.workspaces import WorkspaceRuntimeManager
from tests.test_workflow_mission_control import _blueprint_output


class TonyRuntimeCompositionTests(unittest.TestCase):
    def test_registered_executive_workspace_reads_only_its_bound_workflow_tenant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "runtime"
            workflow_root = root / "workflow-runtime"
            WorkspaceRuntimeManager(runtime_root, root).create(
                "agency", "narratiive", "SAFE Narratiive workspace"
            )
            narratiive = build_tony_workflow_runtime(
                workflow_root,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={},
                environ={},
            )
            narratiive.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-bound-run",
                {"diagnostic_input_package": {"overall_score": 42}},
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            foreign = build_tony_workflow_runtime(
                workflow_root,
                workspace_id="foreign",
                client_id="foreign-client",
                dispatchers={},
                environ={},
            )
            foreign.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-foreign-run",
                {"diagnostic_input_package": {"overall_score": 42}},
                entity_id="safe-foreign-lead",
                correlation_id="safe-foreign-correlation",
            )

            with mock.patch.dict(
                "os.environ",
                {
                    "TONY_WORKFLOW_RUNTIME_ROOT": str(workflow_root),
                    "TONY_OBJECTS_ROOT": str(root / "objects"),
                },
                clear=True,
            ):
                composition = tony_http_bridge.compose_tony_runtime(
                    runtime_root=runtime_root,
                    repository_root=Path(__file__).resolve().parents[1],
                    workspace_id="agency",
                    require_workspace=True,
                    gateway_health_endpoint="",
                )

            states = composition.workflow_backend.list_states()
            self.assertEqual(composition.workspace_id, "agency")
            self.assertEqual(composition.workflow_workspace_id, "narratiive")
            self.assertEqual([state.run_id for state in states], ["safe-bound-run"])
            self.assertEqual(
                [
                    run["run_id"]
                    for run in composition.mission_control_loader().workflow_runs
                ],
                ["safe-bound-run"],
            )

    def test_live_bridge_reuses_composed_workflow_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition = mock.Mock(spec=tony_http_bridge.TonyRuntimeComposition)
            composition.workflow_backend = mock.Mock()
            base = mock.Mock()
            base.command_service = mock.Mock()
            base.bridge_token = ""
            base.brief_archive = mock.Mock()
            base.runtime_composition = composition
            with mock.patch.object(
                tony_live_bridge, "build_base_app", return_value=base
            ) as build_base, mock.patch.object(
                tony_live_bridge, "build_http_dispatchers", return_value={}
            ), mock.patch.dict(
                "os.environ",
                {
                    "TONY_INBOUND_LEADS_PATH": str(root / "leads.json"),
                    "TONY_WORKFLOW_RUNTIME_ROOT": str(root / "workflows"),
                },
                clear=True,
            ):
                app = tony_live_bridge.build_app()

            build_base.assert_called_once_with(dispatchers={})
            self.assertIsInstance(app.workflow_command_service, TonyWorkflowCommandService)
            self.assertIs(
                app.workflow_command_service.backend,
                composition.workflow_backend,
            )

    def test_authenticated_gateway_and_tony_read_the_same_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow_root = root / "workflow-runtime"
            workflow = build_tony_workflow_runtime(
                workflow_root,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={"Claude": lambda _: _blueprint_output()},
                environ={},
            )
            workflow.enqueue(
                "growth_diagnostic_to_blueprint_lite",
                "safe-shared-state-run",
                {
                    "diagnostic_input_package": {"overall_score": 42},
                    "company": "SAFE Shared State Company",
                },
                entity_id="safe-lead",
                correlation_id="safe-correlation",
            )
            workflow.advance(
                "safe-shared-state-run",
                ClientLifecycleRecord(
                    client_id="safe-client",
                    client_name="SAFE Shared State Company",
                    stage=ClientLifecycleStage.BLUEPRINT_LITE,
                    owner="Tony",
                    next_action="Prepare internal work",
                    evidence=("synthetic:test",),
                ),
            )
            with mock.patch.dict(
                "os.environ",
                {
                    "TONY_WORKFLOW_RUNTIME_ROOT": str(workflow_root),
                    "TONY_EXECUTIVE_WORKSPACE_ID": "narratiive",
                    "TONY_OBJECTS_ROOT": str(root / "objects"),
                },
                clear=True,
            ):
                gateway = server.build_app(
                    repository_root=Path(__file__).resolve().parents[1],
                    runtime_root=root / "runtime",
                    api_key="secret",
                )
                composition = tony_http_bridge.compose_tony_runtime(
                    runtime_root=root / "runtime",
                    repository_root=Path(__file__).resolve().parents[1],
                    workspace_id="narratiive",
                    gateway_health_endpoint="",
                    request_surface="runtime-gateway",
                )

            captured = {}
            environ = {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/mission-control",
                "CONTENT_LENGTH": "0",
                "wsgi.input": io.BytesIO(b""),
                "HTTP_AUTHORIZATION": "Bearer secret",
                "HTTP_X_WORKSPACE_ID": "narratiive",
            }
            body = b"".join(
                gateway(
                    environ,
                    lambda status, headers: captured.update(
                        status=status, headers=dict(headers)
                    ),
                )
            )
            public = json.loads(body)
            gateway_run = public["snapshot"]["snapshot"]["workflow_runs"][0]
            tony_run = composition.mission_control_loader().to_dict()[
                "workflow_runs"
            ][0]

            self.assertEqual(captured["status"], "200 OK")
            self.assertEqual(gateway_run, tony_run)
            self.assertEqual(gateway_run["run_id"], "safe-shared-state-run")
            self.assertEqual(gateway_run["status"], "awaiting_approval")
            self.assertFalse(gateway_run["external_action_taken"])
            self.assertEqual(
                public["snapshot"]["domains"]["approvals"]["state"],
                "connected",
            )


if __name__ == "__main__":
    unittest.main()
