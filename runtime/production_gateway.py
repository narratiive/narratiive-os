from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from .wsgi_api import RuntimeWSGIApp


MissionControlSnapshotLoader = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    api_key: str
    idempotency_root: str | Path
    max_body_bytes: int = 1_000_000
    mission_control_workspace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("api_key must not be empty")
        if self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        if self.mission_control_workspace_id is not None and not self.mission_control_workspace_id.strip():
            raise ValueError("mission_control_workspace_id must not be empty")


class FileIdempotencyStore:
    """Atomic response cache keyed by caller-supplied idempotency keys."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: str, request_hash: str, status: str, headers: list[tuple[str, str]], body: bytes) -> None:
        path = self._path(key)
        payload = {
            "request_hash": request_hash,
            "status": status,
            "headers": headers,
            "body": body.decode("utf-8"),
        }
        fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _path(self, key: str) -> Path:
        safe = key.strip()
        if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
            raise ValueError("invalid idempotency key")
        digest = hashlib.sha256(safe.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"


class ProductionGateway:
    """Operational WSGI boundary with auth, correlation and idempotency."""

    def __init__(
        self,
        app: RuntimeWSGIApp,
        config: GatewayConfig,
        mission_control_loader: MissionControlSnapshotLoader | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.mission_control_loader = mission_control_loader
        self.idempotency = FileIdempotencyStore(config.idempotency_root)

    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "")
        correlation_id = environ.get("HTTP_X_CORRELATION_ID") or f"req-{uuid4().hex}"

        if method == "GET" and path in {"/health", "/live", "/ready"}:
            return self._json(start_response, "200 OK", {"ok": True, "status": "ok", "correlation_id": correlation_id}, correlation_id)

        if method == "GET" and path == "/mission-control":
            unauthorized = self._authorize(environ, start_response, correlation_id)
            if unauthorized is not None:
                return unauthorized
            return self._mission_control(environ, start_response, correlation_id)

        if method != "POST" or path != "/commands":
            return self._json(start_response, "404 Not Found", {"ok": False, "error": {"code": "not_found", "message": "not found"}, "correlation_id": correlation_id}, correlation_id)

        unauthorized = self._authorize(environ, start_response, correlation_id)
        if unauthorized is not None:
            return unauthorized

        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            return self._json(start_response, "400 Bad Request", {"ok": False, "error": {"code": "invalid_length", "message": "invalid content length"}, "correlation_id": correlation_id}, correlation_id)
        if length <= 0 or length > self.config.max_body_bytes:
            return self._json(start_response, "413 Payload Too Large", {"ok": False, "error": {"code": "invalid_body_size", "message": "request body size is invalid"}, "correlation_id": correlation_id}, correlation_id)

        body = environ["wsgi.input"].read(length)
        request_hash = hashlib.sha256(body).hexdigest()
        idem_key = (environ.get("HTTP_IDEMPOTENCY_KEY") or "").strip()
        if idem_key:
            try:
                cached = self.idempotency.get(idem_key)
            except ValueError as exc:
                return self._json(start_response, "400 Bad Request", {"ok": False, "error": {"code": "invalid_idempotency_key", "message": str(exc)}, "correlation_id": correlation_id}, correlation_id)
            if cached:
                if cached["request_hash"] != request_hash:
                    return self._json(start_response, "409 Conflict", {"ok": False, "error": {"code": "idempotency_conflict", "message": "idempotency key was used with a different request"}, "correlation_id": correlation_id}, correlation_id)
                headers = [(str(k), str(v)) for k, v in cached["headers"]]
                headers.append(("X-Correlation-ID", correlation_id))
                headers.append(("Idempotency-Replayed", "true"))
                start_response(cached["status"], headers)
                return [cached["body"].encode("utf-8")]

        captured: dict[str, object] = {}

        def capture(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
            captured["status"] = status
            captured["headers"] = list(headers)

        child_environ = dict(environ)
        child_environ["wsgi.input"] = _BytesInput(body)
        response_parts = list(self.app(child_environ, capture))
        response_body = b"".join(response_parts)
        status = str(captured.get("status", "500 Internal Server Error"))
        headers = list(captured.get("headers", []))
        headers.append(("X-Correlation-ID", correlation_id))
        if idem_key and status.startswith("2"):
            self.idempotency.put(idem_key, request_hash, status, headers, response_body)
        start_response(status, headers)
        return [response_body]

    def _authorize(
        self,
        environ: Mapping[str, object],
        start_response: Callable,
        correlation_id: str,
    ) -> list[bytes] | None:
        supplied = str(environ.get("HTTP_AUTHORIZATION", ""))
        expected = f"Bearer {self.config.api_key}"
        if hmac.compare_digest(supplied, expected):
            return None
        return self._json(start_response, "401 Unauthorized", {"ok": False, "error": {"code": "unauthorized", "message": "invalid credentials"}, "correlation_id": correlation_id}, correlation_id)

    def _mission_control(
        self,
        environ: Mapping[str, object],
        start_response: Callable,
        correlation_id: str,
    ) -> list[bytes]:
        configured_workspace = self.config.mission_control_workspace_id
        if self.mission_control_loader is None or configured_workspace is None:
            return self._json(start_response, "503 Service Unavailable", {"ok": False, "error": {"code": "mission_control_unavailable", "message": "Mission Control is not configured"}, "correlation_id": correlation_id}, correlation_id)

        requested_workspace = str(environ.get("HTTP_X_WORKSPACE_ID", "")).strip()
        if not requested_workspace:
            return self._json(start_response, "400 Bad Request", {"ok": False, "error": {"code": "workspace_required", "message": "X-Workspace-ID is required"}, "correlation_id": correlation_id}, correlation_id)
        if not hmac.compare_digest(requested_workspace, configured_workspace):
            return self._json(start_response, "404 Not Found", {"ok": False, "error": {"code": "workspace_not_found", "message": "workspace not found"}, "correlation_id": correlation_id}, correlation_id)

        try:
            snapshot = self.mission_control_loader(configured_workspace)
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                raise TypeError("snapshot must serialize to an object")
        except Exception:
            return self._json(start_response, "503 Service Unavailable", {"ok": False, "error": {"code": "mission_control_untrusted", "message": "Mission Control could not build a trusted snapshot"}, "correlation_id": correlation_id}, correlation_id)

        return self._json(
            start_response,
            "200 OK",
            {
                "ok": True,
                "workspace_id": configured_workspace,
                "snapshot": payload,
                "correlation_id": correlation_id,
            },
            correlation_id,
        )

    @staticmethod
    def _json(start_response: Callable, status: str, payload: Mapping[str, object], correlation_id: str) -> list[bytes]:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        start_response(status, [("Content-Type", "application/json"), ("Content-Length", str(len(body))), ("X-Correlation-ID", correlation_id)])
        return [body]


class _BytesInput:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.data) - self.offset
        chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk
