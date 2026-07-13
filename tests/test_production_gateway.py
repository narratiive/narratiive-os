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


class ProductionGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.stub = StubApp()
        self.gateway = ProductionGateway(
            self.stub,
            GatewayConfig(api_key="secret", idempotency_root=Path(self.tmp.name) / "idem"),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def call(self, *, path="/commands", method="POST", body=b"{}", auth="Bearer secret", idem="", correlation=""):
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "HTTP_AUTHORIZATION": auth,
            "HTTP_IDEMPOTENCY_KEY": idem,
            "HTTP_X_CORRELATION_ID": correlation,
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


if __name__ == "__main__":
    unittest.main()
