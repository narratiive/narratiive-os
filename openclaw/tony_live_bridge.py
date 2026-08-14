from __future__ import annotations

import json
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any
from wsgiref.simple_server import make_server

from openclaw.tony_http_bridge import TonyHTTPBridge, build_app as build_base_app
from runtime.executive_memory import ExecutiveMemoryStore
from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.notion_leads import build_authoritative_lead_loader
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_commercial_watch import TonyCommercialWatchCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService
from runtime.tony_memory_commands import TonyMemoryCommandService
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService
from runtime.tony_terminology_commands import TonyTerminologyCommandService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_FRIDAY_FIELDS = {
    "record_id",
    "occurred_at",
    "record_type",
    "summary",
    "evidence",
    "workspace_id",
}


class LeadAwareTonyApplication:
    """Add lead ingestion and conversational Telegram ingress to Tony's live bridge."""

    def __init__(self, base: TonyHTTPBridge, lead_store: FileInboundLeadStore) -> None:
        self.base = base
        self.lead_store = lead_store

    def __getattr__(self, name: str):
        return getattr(self.base, name)

    def __call__(self, environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "")).upper()
        path = str(environ.get("PATH_INFO", "/")) or "/"
        if method == "POST" and path == "/leads/ingest":
            return self._ingest(environ, start_response)
        if method == "POST" and path == "/telegram/inbound":
            return self._telegram_inbound(environ, start_response)
        return self.base(environ, start_response)

    @staticmethod
    def _is_loopback(environ) -> bool:
        remote = str(environ.get("REMOTE_ADDR", "")).strip().casefold()
        return remote in {"127.0.0.1", "::1", "localhost"}

    def _authorize(self, environ, start_response, *, allow_loopback: bool = False):
        if allow_loopback and self._is_loopback(environ):
            return None
        if not self.base.bridge_token:
            return None
        supplied = str(environ.get("HTTP_AUTHORIZATION", ""))
        if supplied == f"Bearer {self.base.bridge_token}":
            return None
        return self._respond(
            start_response,
            HTTPStatus.UNAUTHORIZED,
            {"ok": False, "error": {"code": "unauthorized", "message": "Invalid bridge token"}},
        )

    def _read_json(self, environ) -> dict[str, Any]:
        length = int(environ.get("CONTENT_LENGTH") or "0")
        raw = environ["wsgi.input"].read(length).decode("utf-8")
        request = json.loads(raw or "{}")
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        return request

    def _telegram_inbound(self, environ, start_response):
        denied = self._authorize(environ, start_response)
        if denied is not None:
            return denied
        try:
            request = self._read_json(environ)
            text = str(request.get("text") or request.get("message") or "").strip()
            if not text:
                raise ValueError("text is required")
            status, payload = self.base._handle_telegram_command(text)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(
                start_response,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_telegram_message", "message": str(exc)}},
            )
        return self._respond(start_response, status, payload)

    def _ingest(self, environ, start_response):
        denied = self._authorize(environ, start_response, allow_loopback=True)
        if denied is not None:
            return denied
        try:
            request = self._read_json(environ)
            payload = request.get("lead") if isinstance(request.get("lead"), dict) else request
            lead = InboundLead.from_mapping(payload)
            self.lead_store.upsert(lead)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(
                start_response,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_lead", "message": str(exc)}},
            )
        except Exception:
            return self._respond(
                start_response,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": {"code": "lead_store_error", "message": "Tony could not persist inbound lead state"}},
            )

        return self._respond(
            start_response,
            HTTPStatus.OK,
            {
                "ok": True,
                "status": "lead_ingested",
                "lead_id": lead.lead_id,
                "contact": lead.contact,
                "source": lead.source,
            },
        )

    @staticmethod
    def _respond(start_response, status: HTTPStatus, payload: dict[str, Any]):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        start_response(
            f"{status.value} {status.phrase}",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]


def load_friday_review_records(root: Path) -> list[dict[str, Any]]:
    """Load a complete trusted Friday evidence store or fail closed."""
    if not root.is_dir():
        raise FileNotFoundError("Friday Review evidence store is unavailable")

    paths = sorted(root.rglob("*.json"))
    if not paths:
        raise ValueError("Friday Review evidence store contains no JSON records")

    records: list[dict[str, Any]] = []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Friday Review evidence file is unreadable: {path.name}") from exc

        candidates = value if isinstance(value, list) else [value]
        if not candidates:
            raise ValueError(f"Friday Review evidence file is empty: {path.name}")
        for candidate in candidates:
            if not isinstance(candidate, dict) or not _REQUIRED_FRIDAY_FIELDS.issubset(candidate):
                raise ValueError(f"Friday Review evidence record is invalid: {path.name}")
            records.append(candidate)

    if not records:
        raise ValueError("Friday Review evidence store contains no records")
    return records


def build_app() -> LeadAwareTonyApplication:
    """Build the production bridge with one coherent deterministic command surface."""
    app = build_base_app()
    if app.command_service is None:
        raise RuntimeError("Tony command service is not configured")

    records_root = Path(
        os.getenv(
            "TONY_FRIDAY_REVIEW_RECORDS_ROOT",
            str(REPOSITORY_ROOT / ".runtime" / "executive-review-records"),
        )
    )
    workspace_id = (
        os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip()
        or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip()
        or "narratiive"
    )
    lead_path = Path(
        os.getenv(
            "TONY_INBOUND_LEADS_PATH",
            str(REPOSITORY_ROOT / ".runtime" / "inbound-leads.json"),
        )
    ).resolve()
    lead_store = FileInboundLeadStore(lead_path)
    authoritative_lead_loader = build_authoritative_lead_loader(lead_store)

    executive_service = TonyExecutiveCommandService(
        app.command_service,
        brief_archive=app.brief_archive,
        friday_record_loader=lambda: load_friday_review_records(records_root),
        workspace_id=workspace_id,
        inbound_lead_loader=authoritative_lead_loader,
    )
    capability_service = TonyCapabilityCommandService(executive_service)
    commercial_commitments_path = Path(
        os.getenv(
            "TONY_COMMERCIAL_COMMITMENTS_PATH",
            str(REPOSITORY_ROOT / ".runtime" / "commercial-commitments.json"),
        )
    )
    commercial_watch_service = TonyCommercialWatchCommandService(
        capability_service,
        store_path=commercial_commitments_path,
    )
    agency_focus_context_path = Path(
        os.getenv(
            "TONY_AGENCY_FOCUS_CONTEXT_PATH",
            str(REPOSITORY_ROOT / ".runtime" / "agency-focus-context.json"),
        )
    )
    agency_focus_service = TonyPersistentAgencyFocusCommandService(
        commercial_watch_service,
        store_path=agency_focus_context_path,
    )
    memory_path = Path(
        os.getenv(
            "TONY_EXECUTIVE_MEMORY_PATH",
            str(REPOSITORY_ROOT / ".runtime" / "executive-memory.jsonl"),
        )
    )
    memory_service = TonyMemoryCommandService(
        agency_focus_service,
        ExecutiveMemoryStore(memory_path),
        agency_id=workspace_id,
    )
    app.command_service = TonyTerminologyCommandService(memory_service)
    return LeadAwareTonyApplication(app, lead_store)


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
