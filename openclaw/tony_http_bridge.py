from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4
from wsgiref.simple_server import make_server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator
from runtime.tony_command_service import CommandResponse, TonyCommandService
from runtime.tony_orchestration import (
    HttpGatewayTransport,
    TonyCommand,
    TonyGatewayError,
    TonyOrchestrationAdapter,
)


ObjectLoader = Callable[[], Iterable[dict[str, Any]]]


class TonyHTTPBridge:
    """Small authenticated HTTP boundary for OpenClaw, Telegram and n8n.

    Telegram slash commands are deliberately handled by the deterministic
    repository-backed command service. They never depend on a managerial LLM,
    so `/status`, `/health`, `/clients`, `/client`, `/next` and `/continue`
    remain available even when a language-model provider is slow or offline.
    """

    def __init__(
        self,
        adapter: TonyOrchestrationAdapter,
        bridge_token: str = "",
        *,
        command_service: TonyCommandService | None = None,
        object_loader: ObjectLoader | None = None,
    ) -> None:
        self.adapter = adapter
        self.bridge_token = bridge_token.strip()
        self.command_service = command_service
        self.object_loader = object_loader

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
        method = str(environ.get("REQUEST_METHOD", "")).upper()
        path = str(environ.get("PATH_INFO", "/")) or "/"

        if method == "GET" and path == "/health":
            return HTTPStatus.OK, {
                "ok": True,
                "service": "tony-http-bridge",
                "status": "alive",
                "deterministic_commands": self.command_service is not None,
            }

        if method != "POST":
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

        telegram_command = self._extract_telegram_command(request)
        if telegram_command is not None:
            return self._handle_telegram_command(telegram_command)

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
            "reply": response.message,
            "command": response.command,
            "command_id": command_id,
            "correlation_id": response.correlation_id,
            "data": response.data,
        }

    def _handle_telegram_command(self, command: str):
        if self.command_service is None or self.object_loader is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, self._error(
                "command_service_unavailable",
                "Repository-backed Tony commands are not configured",
            )
        try:
            objects = list(self.object_loader())
            response = self.command_service.execute(command, objects)
        except Exception:
            return HTTPStatus.SERVICE_UNAVAILABLE, self._error(
                "repository_state_unavailable",
                "Tony could not read repository state",
            )
        payload = response.to_dict()
        reply = self._format_telegram_reply(response)
        return HTTPStatus.OK, {
            "ok": response.status != "error",
            "reply": reply,
            "message": reply,
            **payload,
        }

    @staticmethod
    def _extract_telegram_command(request: dict[str, Any]) -> str | None:
        candidates: list[Any] = [request.get("text"), request.get("message")]
        body = request.get("body")
        if isinstance(body, dict):
            candidates.extend([body.get("text"), body.get("message")])
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("text")
            if isinstance(candidate, str):
                normalized = candidate.strip()
                if normalized.startswith("/"):
                    return normalized
        return None

    @staticmethod
    def _format_telegram_reply(response: CommandResponse) -> str:
        lines = [response.message]
        data = response.data
        if response.command in {"status", "progress", "progress_update"}:
            lines.append(f"Campaigns: {data.get('campaign_count', 0)}")
            lines.append(f"Blocked: {data.get('blocked_count', 0)}")
        elif response.command == "health":
            validation = data.get("validation", {})
            lines.append(f"Objects validated: {validation.get('objects_validated', 0)}")
        elif response.command == "client":
            campaigns = data.get("campaigns", [])
            if campaigns:
                current = campaigns[0]
                lines.append(f"Stage: {current.get('current_stage', 'unknown')}")
                lines.append(f"Next: {current.get('next_action', 'No action available')}")
        elif response.command in {"next", "what_next", "continue"}:
            primary = data.get("primary", {})
            if primary:
                lines.append(f"Stage: {primary.get('current_stage', 'unknown')}")
                lines.append(f"Owner action: {primary.get('next_action', 'No action available')}")
        if response.status == "blocked":
            lines.append("Status: blocked")
        elif response.status == "error":
            lines.append(f"Error: {data.get('error_code', 'unknown_error')}")
        return "\n".join(lines)[:3500]

    @staticmethod
    def _error(code: str, message: str):
        return {"ok": False, "error": {"code": code, "message": message}}


def load_growth_objects(root: Path) -> list[dict[str, Any]]:
    """Load canonical object records while ignoring schemas and unrelated JSON."""
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("id") and candidate.get("object_type"):
                records.append(candidate)
    return records


def build_app() -> TonyHTTPBridge:
    api_key = os.getenv("NARRATIIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("NARRATIIVE_API_KEY is required")
    endpoint = os.getenv("NARRATIIVE_GATEWAY_ENDPOINT", "http://127.0.0.1:8787/")
    bridge_token = os.getenv("TONY_BRIDGE_TOKEN", "")
    gateway_timeout = float(os.getenv("TONY_GATEWAY_TIMEOUT_SECONDS", "25"))
    adapter = TonyOrchestrationAdapter(HttpGatewayTransport(endpoint, api_key, timeout_seconds=gateway_timeout))

    schema_path = Path(os.getenv(
        "TONY_GROWTH_OBJECT_SCHEMA",
        str(REPOSITORY_ROOT / "schemas" / "shared" / "growth-object.schema.json"),
    ))
    objects_root = Path(os.getenv("TONY_OBJECTS_ROOT", str(REPOSITORY_ROOT / "clients")))
    validator = GrowthObjectValidator.from_path(schema_path)
    command_service = TonyCommandService(RepositoryProgressEngine(validator))
    return TonyHTTPBridge(
        adapter,
        bridge_token,
        command_service=command_service,
        object_loader=lambda: load_growth_objects(objects_root),
    )


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
