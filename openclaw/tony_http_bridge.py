from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from pathlib import Path
from uuid import uuid4
from wsgiref.simple_server import make_server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.tony_orchestration import (
    HttpGatewayTransport,
    TonyCommand,
    TonyGatewayError,
    TonyOrchestrationAdapter,
)


class TonyHTTPBridge:
    """Small authenticated HTTP boundary for OpenClaw, Telegram and n8n."""

    def __init__(self, adapter: TonyOrchestrationAdapter, bridge_token: str = "") -> None:
        self.adapter = adapter
        self.bridge_token = bridge_token.strip()

    def __call__(self, environ, start_response):
        try:
            status, payload = self.handle(environ)
        except Exception:
            status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {
                "ok": False,
                "error": {"code": "bridge_error", "message": "Tony bridge failed"},
            }
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        start_response(
            f"{status.value} {status.phrase}",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]

    def handle(self, environ):
        if environ.get("REQUEST_METHOD") != "POST":
            return HTTPStatus.METHOD_NOT_ALLOWED, self._error("method_not_allowed", "POST required")
        if self.bridge_token:
            supplied = str(environ.get("HTTP_AUTHORIZATION", ""))
            if supplied != f"Bearer {self.bridge_token}":
                return HTTPStatus.UNAUTHORIZED, self._error("unauthorized", "Invalid bridge token")
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
            raw = environ["wsgi.input"].read(length).decode("utf-8")
            request = json.loads(raw or "{}")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return HTTPStatus.BAD_REQUEST, self._error("invalid_json", "Request must be valid JSON")
        if not isinstance(request, dict):
            return HTTPStatus.BAD_REQUEST, self._error("invalid_request", "Request must be an object")
        required = ("action", "workspace_id", "client_id")
        missing = [name for name in required if not str(request.get(name, "")).strip()]
        if missing:
            return HTTPStatus.BAD_REQUEST, self._error("missing_fields", ", ".join(missing))
        command_id = str(request.get("command_id", "")).strip() or f"bridge-{uuid4().hex}"
        try:
            response = self.adapter.execute(
                TonyCommand(
                    action=str(request["action"]),
                    workspace_id=str(request["workspace_id"]),
                    client_id=str(request["client_id"]),
                    command_id=command_id,
                    reviewer_id=str(request.get("reviewer_id", "")),
                    rationale=str(request.get("rationale", "")),
                    payload=request.get("payload") if isinstance(request.get("payload"), dict) else {},
                )
            )
        except TonyGatewayError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if exc.retryable else HTTPStatus.BAD_REQUEST
            return status, {
                "ok": False,
                "command_id": command_id,
                "error": {"code": exc.code, "message": str(exc), "retryable": exc.retryable},
            }
        return HTTPStatus.OK, {
            "ok": True,
            "message": response.message,
            "command": response.command,
            "command_id": command_id,
            "correlation_id": response.correlation_id,
            "data": response.data,
        }

    @staticmethod
    def _error(code: str, message: str):
        return {"ok": False, "error": {"code": code, "message": message}}


def build_app() -> TonyHTTPBridge:
    api_key = os.getenv("NARRATIIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("NARRATIIVE_API_KEY is required")
    endpoint = os.getenv("NARRATIIVE_GATEWAY_ENDPOINT", "http://127.0.0.1:8787/")
    bridge_token = os.getenv("TONY_BRIDGE_TOKEN", "")
    adapter = TonyOrchestrationAdapter(HttpGatewayTransport(endpoint, api_key, timeout_seconds=60))
    return TonyHTTPBridge(adapter, bridge_token)


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
