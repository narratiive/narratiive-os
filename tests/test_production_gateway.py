import io
import json
import tempfile
import unittest
from pathlib import Path

from runtime.production_gateway import GatewayConfig, ProductionGateway


class StubApp:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, environ, start_response):
        self.calls += 1
        body = json.dumps({"ok": True, "calls": self.calls}).encode("utf-8")
        start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]


class StubSnapshot:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


class ProductionGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.stub = StubApp()
        self.loaded_workspaces = []

        def load_snapshot(workspace_id):
            self.loaded_workspaces.append(workspace_id)
            return StubSnapshot(
                {
                    "generated_at": "2026-07-30T12:00:00Z",
                    "status": "partial",
                    "connections": [
                        {"name": "commercial_pipeline", "state": "not_connected"},
                        {"name": "publishing", "state": "not_connected"},
                    ],
                    "recommended_focus_details": [
                        {
                            "action": "advance:mission-control:publish read model",
                            "category": "workstream",
                            "confidence": "high",
                            "evidence": ["workstreams/0"],
                        }
                    ],
                }
            )

        self.gateway = ProductionGateway(
            self.stub,
            GatewayConfig(
                api_key="secret",
                idempotency_root=Path(self.tmp.name) / "idem",
                mission_control_workspace_id="narratiive",
            ),
            mission_control_loader=load_snapshot,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def call(
        self,
        *,
        path="/commands",
        method="POST",
        body=b"{}",
        auth="Bearer secret",
        idem="",
        correlation="",
        workspace="narratiive",
    ):
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "HTTP_AUTHORIZATION": auth,
            "HTTP_IDEMPOTENCY_KEY": idem,
            "HTTP_X_CORRELATION_ID": correlation,
            "HTTP_X_WORKSPACE_ID": workspace,
        }
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = dict(headers)

        payload = b"".join(self.gateway(environ, start_response))
        return captured, json.loads(payload.decode("utf-8"))

    def test_health_is_public(self) -> None:
        captured, payload = self.call(path="/health", method="GET", body=b"", auth="")
        self.assertEqual(captured["status"], "200 OK")
        self.assertTrue(payload["ok"])

    def test_commands_require_bearer_token(self) -> None:
        captured, payload = self.call(auth="Bearer wrong")
        self.assertEqual(captured["status"], "401 Unauthorized")
        self.assertEqual(payload["error"]["code"], "unauthorized")
        self.assertEqual(self.stub.calls, 0)

    def test_correlation_id_is_returned(self) -> None:
        captured, _ = self.call(correlation="corr-123")
        self.assertEqual(captured["headers"]["X-Correlation-ID"], "corr-123")

    def test_idempotent_request_is_replayed(self) -> None:
        first, first_payload = self.call(idem="create-run-1")
        second, second_payload = self.call(idem="create-run-1")
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(self.stub.calls, 1)
        self.assertEqual(second["headers"]["Idempotency-Replayed"], "true")

    def test_reusing_key_with_different_body_conflicts(self) -> None:
        self.call(idem="same-key", body=b'{"a":1}')
        captured, payload = self.call(idem="same-key", body=b'{"a":2}')
        self.assertEqual(captured["status"], "409 Conflict")
        self.assertEqual(payload["error"]["code"], "idempotency_conflict")

    def test_invalid_idempotency_key_is_rejected(self) -> None:
        captured, payload = self.call(idem="../bad")
        self.assertEqual(captured["status"], "400 Bad Request")
        self.assertEqual(payload["error"]["code"], "invalid_idempotency_key")

    def test_mission_control_read_requires_authentication(self) -> None:
        captured, payload = self.call(
            path="/mission-control",
            method="GET",
            body=b"",
            auth="Bearer wrong",
        )
        self.assertEqual(captured["status"], "401 Unauthorized")
        self.assertEqual(payload["error"]["code"], "unauthorized")
        self.assertEqual(self.loaded_workspaces, [])

    def test_mission_control_read_returns_canonical_snapshot(self) -> None:
        captured, payload = self.call(
            path="/mission-control",
            method="GET",
            body=b"",
            correlation="mission-123",
        )
        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(captured["headers"]["X-Correlation-ID"], "mission-123")
        self.assertEqual(payload["workspace_id"], "narratiive")
        self.assertEqual(payload["snapshot"]["status"], "partial")
        self.assertEqual(
            payload["snapshot"]["connections"],
            [
                {"name": "commercial_pipeline", "state": "not_connected"},
                {"name": "publishing", "state": "not_connected"},
            ],
        )
        self.assertEqual(
            payload["snapshot"]["recommended_focus_details"][0]["evidence"],
            ["workstreams/0"],
        )
        self.assertEqual(
            payload["snapshot"]["recommended_focus_details"][0]["confidence"],
            "high",
        )
        self.assertEqual(self.loaded_workspaces, ["narratiive"])

    def test_mission_control_read_fails_closed_for_cross_workspace_request(self) -> None:
        captured, payload = self.call(
            path="/mission-control",
            method="GET",
            body=b"",
            workspace="another-workspace",
        )
        self.assertEqual(captured["status"], "404 Not Found")
        self.assertEqual(payload["error"]["code"], "workspace_not_found")
        self.assertEqual(self.loaded_workspaces, [])

    def test_mission_control_read_requires_workspace_scope(self) -> None:
        captured, payload = self.call(
            path="/mission-control",
            method="GET",
            body=b"",
            workspace="",
        )
        self.assertEqual(captured["status"], "400 Bad Request")
        self.assertEqual(payload["error"]["code"], "workspace_required")
        self.assertEqual(self.loaded_workspaces, [])

    def test_mission_control_read_is_deterministic_and_non_mutating(self) -> None:
        first, first_payload = self.call(path="/mission-control", method="GET", body=b"")
        second, second_payload = self.call(path="/mission-control", method="GET", body=b"")
        self.assertEqual(first["status"], "200 OK")
        self.assertEqual(second["status"], "200 OK")
        first_payload.pop("correlation_id")
        second_payload.pop("correlation_id")
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(self.stub.calls, 0)

    def test_mission_control_read_reports_unavailable_configuration(self) -> None:
        gateway = ProductionGateway(
            self.stub,
            GatewayConfig(api_key="secret", idempotency_root=Path(self.tmp.name) / "other"),
        )
        previous = self.gateway
        self.gateway = gateway
        try:
            captured, payload = self.call(
                path="/mission-control",
                method="GET",
                body=b"",
            )
        finally:
            self.gateway = previous
        self.assertEqual(captured["status"], "503 Service Unavailable")
        self.assertEqual(payload["error"]["code"], "mission_control_unavailable")


if __name__ == "__main__":
    unittest.main()
