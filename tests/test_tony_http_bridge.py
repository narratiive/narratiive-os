import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_http_bridge import (
    TonyHTTPBridge,
    build_github_components,
    build_mission_control_loader,
)
from runtime.github_work import GitHubWorkItem, GitHubWorkSnapshot
from runtime.mission_control import MissionControlBuilder
from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator
from runtime.tony_command_service import TonyCommandService
from runtime.tony_orchestration import FakeGatewayTransport, TonyOrchestrationAdapter
from runtime.workspaces import WorkspaceRuntimeManager


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "shared" / "growth-object.schema.json"


def object_record():
    return {
        "id": "growth_specification:rave:launch",
        "object_type": "growth_specification",
        "version": "1.0",
        "client_id": "rave",
        "client_name": "Rave Coffee",
        "campaign_id": "launch",
        "campaign_name": "National Growth",
        "status": "approved",
        "created_at": "2026-07-22T20:00:00Z",
        "updated_at": "2026-07-22T20:00:00Z",
        "created_by": "tony",
        "approved_by": "matt",
        "approved_at": "2026-07-22T21:00:00Z",
        "parent_object_id": None,
        "source_object_ids": [],
        "child_object_ids": [],
        "repository_path": "clients/rave/launch/growth_specification.json",
        "commit_sha": None,
    }


class TonyHTTPBridgeTests(unittest.TestCase):
    def request(self, bridge, payload, token="", path="/"):
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
            "HTTP_AUTHORIZATION": f"Bearer {token}" if token else "",
        }
        return bridge.handle(environ)

    def command_bridge(self, transport=None, diagnostics_runner=None, mission_control_loader=None):
        transport = transport or FakeGatewayTransport()
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        progress_engine = RepositoryProgressEngine(validator)
        service = TonyCommandService(
            progress_engine,
            mission_control_loader=mission_control_loader,
        )
        return TonyHTTPBridge(
            TonyOrchestrationAdapter(transport),
            command_service=service,
            object_loader=lambda: [object_record()],
            diagnostics_runner=diagnostics_runner,
        ), transport

    def test_health_endpoint_is_available_without_gateway_or_token(self):
        transport = FakeGatewayTransport()
        bridge = TonyHTTPBridge(TonyOrchestrationAdapter(transport), "bridge-secret")
        status, response = bridge.handle({"REQUEST_METHOD": "GET", "PATH_INFO": "/health"})
        self.assertEqual(status.value, 200)
        self.assertEqual(response["service"], "tony-http-bridge")
        self.assertEqual(response["status"], "alive")
        self.assertFalse(response["deterministic_commands"])
        self.assertFalse(response["diagnostics"])
        self.assertFalse(response["mission_control"])
        self.assertFalse(response["github"])
        self.assertEqual(transport.calls, [])

    def test_health_endpoint_reports_mission_control_configuration(self):
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        progress_engine = RepositoryProgressEngine(validator)
        loader = build_mission_control_loader(
            progress_engine,
            lambda: [object_record()],
            "http://127.0.0.1:1/health",
        )
        bridge, _ = self.command_bridge(mission_control_loader=loader)
        status, response = bridge.handle({"REQUEST_METHOD": "GET", "PATH_INFO": "/health"})
        self.assertEqual(status.value, 200)
        self.assertTrue(response["mission_control"])

    def test_forwards_health_command_and_preserves_ids(self):
        transport = FakeGatewayTransport([
            {"ok": True, "command": "health", "data": {"status": "ok"}}
        ])
        bridge = TonyHTTPBridge(TonyOrchestrationAdapter(transport), "bridge-secret")
        status, response = self.request(
            bridge,
            {
                "action": "health",
                "workspace_id": "rave",
                "client_id": "rave-client",
                "command_id": "health-1",
            },
            token="bridge-secret",
        )
        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["command_id"], "health-1")
        self.assertEqual(response["reply"], "Narratiive OS health: ok.")
        self.assertEqual(transport.calls[0]["payload"]["command"], "health")
        self.assertEqual(transport.calls[0]["idempotency_key"], "health-1")

    def test_rejects_bad_token_before_gateway(self):
        transport = FakeGatewayTransport()
        bridge = TonyHTTPBridge(TonyOrchestrationAdapter(transport), "bridge-secret")
        status, response = self.request(
            bridge,
            {"action": "health", "workspace_id": "rave", "client_id": "rave-client"},
            token="wrong",
        )
        self.assertEqual(status.value, 401)
        self.assertEqual(response["error"]["code"], "unauthorized")
        self.assertEqual(transport.calls, [])

    def test_requires_identity_fields(self):
        bridge = TonyHTTPBridge(TonyOrchestrationAdapter(FakeGatewayTransport()))
        status, response = self.request(bridge, {"action": "health"})
        self.assertEqual(status.value, 400)
        self.assertEqual(response["error"]["code"], "missing_fields")

    def test_status_slash_command_bypasses_gateway_and_managerial_llm(self):
        bridge, transport = self.command_bridge()
        status, response = self.request(bridge, {"message": {"text": "/status"}}, path="/telegram")
        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["command"], "status")
        self.assertIn("Campaigns: 1", response["reply"])
        self.assertEqual(transport.calls, [])

    def test_nested_n8n_body_command_is_supported(self):
        bridge, transport = self.command_bridge()
        status, response = self.request(
            bridge,
            {"body": {"message": {"text": "/client Rave"}}},
            path="/telegram",
        )
        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertIn("Rave Coffee", response["reply"])
        self.assertIn("Stage: growth_blueprint", response["reply"])
        self.assertEqual(transport.calls, [])

    def test_mission_command_returns_live_snapshot_without_gateway_dispatch(self):
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        progress_engine = RepositoryProgressEngine(validator)
        loader = build_mission_control_loader(
            progress_engine,
            lambda: [object_record()],
            "http://127.0.0.1:1/health",
        )
        bridge, transport = self.command_bridge(mission_control_loader=loader)
        status, response = self.request(bridge, {"text": "/mission"}, path="/telegram")
        self.assertEqual(status.value, 200)
        self.assertEqual(response["command"], "mission")
        self.assertIn("Mission Control is blocked", response["reply"])
        self.assertIn("connection:runtime-gateway:degraded", response["reply"])
        self.assertEqual(transport.calls, [])

    def test_diagnostics_command_reports_each_runtime_layer_without_gateway_dispatch(self):
        report = {
            "ok": True,
            "checks": [
                {"name": "tony-http-bridge", "healthy": True, "error": ""},
                {"name": "runtime-gateway", "healthy": True, "error": ""},
                {"name": "repository-state", "healthy": True, "error": ""},
            ],
        }
        bridge, transport = self.command_bridge(diagnostics_runner=lambda: report)
        status, response = self.request(bridge, {"text": "/diagnostics"}, path="/telegram")
        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["command"], "diagnostics")
        self.assertIn("Tony diagnostics: healthy.", response["reply"])
        self.assertIn("OK — repository-state", response["reply"])
        self.assertEqual(transport.calls, [])

    def test_diagnostics_command_returns_specific_degraded_component(self):
        report = {
            "ok": False,
            "checks": [
                {"name": "tony-http-bridge", "healthy": True, "error": ""},
                {"name": "runtime-gateway", "healthy": False, "error": "connection refused"},
                {"name": "repository-state", "healthy": True, "error": ""},
            ],
        }
        bridge, _ = self.command_bridge(diagnostics_runner=lambda: report)
        status, response = self.request(bridge, {"text": "/doctor"}, path="/telegram")
        self.assertEqual(status.value, 200)
        self.assertFalse(response["ok"])
        self.assertEqual(response["status"], "degraded")
        self.assertIn("FAIL — runtime-gateway: connection refused", response["reply"])

    def test_diagnostics_unavailable_has_explicit_error(self):
        bridge, _ = self.command_bridge()
        status, response = self.request(bridge, {"text": "/diagnostics"}, path="/telegram")
        self.assertEqual(status.value, 503)
        self.assertEqual(response["error"]["code"], "diagnostics_unavailable")

    def test_non_slash_payload_keeps_existing_gateway_contract(self):
        transport = FakeGatewayTransport([
            {"ok": True, "command": "health", "data": {"status": "ok"}}
        ])
        bridge, _ = self.command_bridge(transport)
        status, response = self.request(
            bridge,
            {"action": "health", "workspace_id": "rave", "client_id": "rave"},
        )
        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(len(transport.calls), 1)

    def test_github_command_returns_live_work_without_gateway_dispatch(self):
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        progress_engine = RepositoryProgressEngine(validator)
        pull = GitHubWorkItem(
            kind="pull_request",
            number=66,
            title="GitHub awareness",
            url="https://github.test/pull/66",
            state="open",
            author="codex",
            created_at="2026-07-24T10:00:00Z",
            updated_at="2026-07-24T11:00:00Z",
            head_sha="abc",
            requested_reviewers=("matt",),
        )
        github = GitHubWorkSnapshot(
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            observed_at="2026-07-24T11:00:00Z",
            baseline_status="unavailable",
            baseline_artifact_id="",
            open_pull_requests=(pull,),
            active_issues=(),
            blocked=(),
            matt_approval_required=(pull,),
            changes_since_previous_brief=(),
        )

        def loader():
            return MissionControlBuilder().build(
                generated_at="2026-07-24T11:00:00Z",
                progress=progress_engine.build_snapshot([object_record()]),
                connections={"GitHub": {"state": "connected"}},
                github_work=github,
            )

        bridge, transport = self.command_bridge(mission_control_loader=loader)
        bridge.command_service.github_configured = True

        status, response = self.request(
            bridge, {"text": "/github"}, path="/telegram"
        )

        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertIn("Open pull requests:", response["reply"])
        self.assertIn("Requires Matt review:", response["reply"])
        self.assertIn("baseline unavailable", response["reply"])
        self.assertEqual(transport.calls, [])

    def test_github_components_require_complete_config_and_existing_workspace(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            loader, archive = build_github_components(
                runtime_root=Path("/tmp/runtime"),
                repository_root=ROOT,
            )
        self.assertIsNone(loader)
        self.assertIsNone(archive)

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        runtime_root = Path(temporary.name)
        WorkspaceRuntimeManager(runtime_root, ROOT).create(
            "agency", "agency-client", "Agency"
        )
        environment = {
            "TONY_GITHUB_REPOSITORY": "narratiive/narratiive-os",
            "TONY_GITHUB_WORKSPACE_ID": "agency",
            "TONY_GITHUB_MATT_LOGIN": "matt",
            "TONY_GITHUB_TOKEN": "read-only",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            loader, archive = build_github_components(
                runtime_root=runtime_root,
                repository_root=ROOT,
            )

        self.assertIsNotNone(loader)
        self.assertEqual(archive.workspace_id, "agency")


if __name__ == "__main__":
    unittest.main()
