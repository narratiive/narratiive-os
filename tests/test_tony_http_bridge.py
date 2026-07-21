import io
import json
import unittest

from openclaw.tony_http_bridge import TonyHTTPBridge
from runtime.tony_orchestration import FakeGatewayTransport, TonyOrchestrationAdapter


class TonyHTTPBridgeTests(unittest.TestCase):
    def request(self, bridge, payload, token=""):
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
            "HTTP_AUTHORIZATION": f"Bearer {token}" if token else "",
        }
        return bridge.handle(environ)

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


if __name__ == "__main__":
    unittest.main()
