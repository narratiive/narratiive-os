import io
import json
import tempfile
import unittest
from pathlib import Path

from openclaw.tony_http_bridge import TonyHTTPBridge, load_mission_control_snapshot
from runtime.mission_control import ConnectionStatus, MissionControlSnapshot, WorkstreamStatus
from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator
from runtime.tony_command_service import TonyCommandService
from runtime.tony_executive_service import TonyExecutiveService
from runtime.tony_orchestration import FakeGatewayTransport, TonyOrchestrationAdapter


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


def mission_control_snapshot():
    return MissionControlSnapshot(
        generated_at="2026-07-24T02:00:00Z",
        status="partial",
        progress={"status": "healthy", "campaigns": []},
        workstreams=(
            WorkstreamStatus(
                workstream_id="mission-control",
                title="Mission Control",
                state="tested",
                owner="Tony",
                next_action="Validate the live bridge.",
                evidence=("commit:12d64fa",),
            ),
        ),
        connections=(
            ConnectionStatus(
                name="notion",
                state="unknown",
                evidence="No live check recorded.",
            ),
        ),
        approvals_required=(),
        blockers=(),
    )


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

    def command_bridge(self, transport=None, diagnostics_runner=None, snapshot_loader=None):
        transport = transport or FakeGatewayTransport()
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        service = TonyCommandService(RepositoryProgressEngine(validator))
        executive_service = TonyExecutiveService(service) if snapshot_loader is not None else None
        return TonyHTTPBridge(
            TonyOrchestrationAdapter(transport),
            command_service=service,
            object_loader=lambda: [object_record()],
            diagnostics_runner=diagnostics_runner,
            executive_service=executive_service,
            mission_control_loader=snapshot_loader,
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
        self.assertFalse(response["executive_commands"])
        self.assertEqual(transport.calls, [])

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

    def test_mission_control_command_uses_recorded_snapshot_without_gateway(self):
        bridge, transport = self.command_bridge(snapshot_loader=mission_control_snapshot)
        status, response = self.request(bridge, {"text": "/overview"}, path="/telegram")
        self.assertEqual(status.value, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["command"], "mission_control")
        self.assertIn("Mission Control is partial", response["reply"])
        self.assertEqual(transport.calls, [])

    def test_mission_control_command_fails_closed_without_snapshot(self):
        bridge, transport = self.command_bridge(snapshot_loader=lambda: None)
        status, response = self.request(bridge, {"text": "/mission_control"}, path="/telegram")
        self.assertEqual(status.value, 200)
        self.assertFalse(response["ok"])
        self.assertEqual(response["data"]["error_code"], "mission_control_unavailable")
        self.assertEqual(transport.calls, [])

    def test_snapshot_loader_rejects_invalid_and_loads_recorded_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mission-control.json"
            self.assertIsNone(load_mission_control_snapshot(path))
            path.write_text("not-json", encoding="utf-8")
            self.assertIsNone(load_mission_control_snapshot(path))
            path.write_text(json.dumps(mission_control_snapshot().to_dict()), encoding="utf-8")
            loaded = load_mission_control_snapshot(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.status, "partial")
            self.assertEqual(loaded.workstreams[0].workstream_id, "mission-control")

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


if __name__ == "__main__":
    unittest.main()
