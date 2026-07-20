from __future__ import annotations

import json
from typing import Callable, Iterable

from .command_api import CommandError, RuntimeCommandAPI


class RuntimeWSGIApp:
    """Minimal JSON-over-HTTP gateway for the structured command API."""

    def __init__(self, api: RuntimeCommandAPI, max_body_bytes: int = 1_000_000) -> None:
        self.api = api
        self.max_body_bytes = max_body_bytes

    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:
        if environ.get("REQUEST_METHOD") != "POST" or environ.get("PATH_INFO") != "/commands":
            return self._respond(start_response, 404, {"ok": False, "error": {"code": "not_found", "message": "not found"}})

        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            return self._respond(start_response, 400, {"ok": False, "error": {"code": "invalid_length", "message": "invalid content length"}})
        if length <= 0 or length > self.max_body_bytes:
            return self._respond(start_response, 413, {"ok": False, "error": {"code": "invalid_body_size", "message": "request body size is invalid"}})

        try:
            body = environ["wsgi.input"].read(length).decode("utf-8")
            request = json.loads(body)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            payload = self.api.handle(request)
            return self._respond(start_response, 200, payload)
        except CommandError as exc:
            return self._respond(start_response, exc.status, {"ok": False, "error": {"code": exc.code, "message": str(exc)}})
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return self._respond(start_response, 400, {"ok": False, "error": {"code": "invalid_json", "message": str(exc)}})
        except Exception:
            return self._respond(start_response, 500, {"ok": False, "error": {"code": "internal_error", "message": "internal server error"}})

    @staticmethod
    def _respond(start_response: Callable, status: int, payload: dict) -> list[bytes]:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        start_response(
            f"{status} {_reason(status)}",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]


def _reason(status: int) -> str:
    return {
        200: "OK",
        400: "Bad Request",
        404: "Not Found",
        409: "Conflict",
        413: "Payload Too Large",
        503: "Service Unavailable",
        500: "Internal Server Error",
    }.get(status, "Error")
