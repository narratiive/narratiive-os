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
from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_commercial_autonomous_judgement import TonyCommercialAutonomousJudgementCommandService
from runtime.tony_commercial_close import TonyCommercialCloseCommandService
from runtime.tony_commercial_followup import TonyCommercialFollowupCommandService
from runtime.tony_commercial_watch import TonyCommercialWatchCommandService
from runtime.tony_confirmed_meeting_booking import TonyConfirmedMeetingBookingCommandService
from runtime.tony_delivery_blueprint_review import TonyDeliveryBlueprintReviewCommandService
from runtime.tony_delivery_bootstrap import TonyDeliveryBootstrapCommandService
from runtime.tony_delivery_commissioning import TonyDeliveryCommissioningCommandService
from runtime.tony_discovery_outcome_tracking import TonyDiscoveryOutcomeTrackingCommandService
from runtime.tony_dispatch_adapters import build_http_dispatchers
from runtime.tony_drive_delivery_workspace import TonyDriveDeliveryWorkspaceCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService
from runtime.tony_executive_learning import TonyExecutiveLearningCommandService
from runtime.tony_meeting_reply_preparation import TonyMeetingReplyPreparationCommandService
from runtime.tony_memory_commands import TonyMemoryCommandService
from runtime.tony_outcome_accountability import TonyOutcomeAccountabilityCommandService
from runtime.tony_outcome_evidence import TonyOutcomeEvidenceCommandService
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService
from runtime.tony_post_booking_notion_sync import TonyPostBookingNotionSyncCommandService
from runtime.tony_post_discovery_commercial import TonyPostDiscoveryCommercialCommandService
from runtime.tony_post_discovery_proposal_execution import TonyPostDiscoveryProposalExecutionCommandService
from runtime.tony_post_send_notion_sync import TonyPostSendNotionSyncCommandService
from runtime.tony_proposal_outcome_tracking import TonyProposalOutcomeTrackingCommandService
from runtime.tony_terminology_commands import TonyTerminologyCommandService
from runtime.tony_verified_execution_status import TonyVerifiedExecutionStatusCommandService

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_FRIDAY_FIELDS = {"record_id", "occurred_at", "record_type", "summary", "evidence", "workspace_id"}

class LeadAwareTonyApplication:
    def __init__(self, base: TonyHTTPBridge, lead_store: FileInboundLeadStore) -> None: self.base = base; self.lead_store = lead_store
    def __getattr__(self, name: str): return getattr(self.base, name)
    def __call__(self, environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "")).upper(); path = str(environ.get("PATH_INFO", "/")) or "/"
        if method == "POST" and path == "/leads/ingest": return self._ingest(environ, start_response)
        if method == "POST" and path == "/telegram/inbound": return self._telegram_inbound(environ, start_response)
        return self.base(environ, start_response)
    @staticmethod
    def _is_loopback(environ) -> bool: return str(environ.get("REMOTE_ADDR", "")).strip().casefold() in {"127.0.0.1", "::1", "localhost"}
    def _authorize(self, environ, start_response, *, allow_loopback: bool = False):
        if allow_loopback and self._is_loopback(environ): return None
        if not self.base.bridge_token: return None
        if str(environ.get("HTTP_AUTHORIZATION", "")) == f"Bearer {self.base.bridge_token}": return None
        return self._respond(start_response, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": {"code": "unauthorized", "message": "Invalid bridge token"}})
    def _read_json(self, environ) -> dict[str, Any]:
        length = int(environ.get("CONTENT_LENGTH") or "0"); raw = environ["wsgi.input"].read(length).decode("utf-8"); request = json.loads(raw or "{}")
        if not isinstance(request, dict): raise ValueError("request must be an object")
        return request
    def _telegram_inbound(self, environ, start_response):
        denied = self._authorize(environ, start_response)
        if denied is not None: return denied
        try:
            request = self._read_json(environ); text = str(request.get("text") or request.get("message") or "").strip()
            if not text: raise ValueError("text is required")
            status, payload = self.base._handle_telegram_command(text)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc: return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_telegram_message", "message": str(exc)}})
        return self._respond(start_response, status, payload)
    def _ingest(self, environ, start_response):
        denied = self._authorize(environ, start_response, allow_loopback=True)
        if denied is not None: return denied
        try:
            request = self._read_json(environ); payload = request.get("lead") if isinstance(request.get("lead"), dict) else request; lead = InboundLead.from_mapping(payload); self.lead_store.upsert(lead)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc: return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_lead", "message": str(exc)}})
        except Exception: return self._respond(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": {"code": "lead_store_error", "message": "Tony could not persist inbound lead state"}})
        return self._respond(start_response, HTTPStatus.OK, {"ok": True, "status": "lead_ingested", "lead_id": lead.lead_id, "contact": lead.contact, "source": lead.source})
    @staticmethod
    def _respond(start_response, status: HTTPStatus, payload: dict[str, Any]):
        body = json.dumps(payload, sort_keys=True).encode("utf-8"); start_response(f"{status.value} {status.phrase}", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]); return [body]

def load_friday_review_records(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir(): raise FileNotFoundError("Friday Review evidence store is unavailable")
    paths = sorted(root.rglob("*.json"))
    if not paths: raise ValueError("Friday Review evidence store contains no JSON records")
    records: list[dict[str, Any]] = []
    for path in paths:
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError(f"Friday Review evidence file is unreadable: {path.name}") from exc
        candidates = value if isinstance(value, list) else [value]
        if not candidates: raise ValueError(f"Friday Review evidence file is empty: {path.name}")
        for candidate in candidates:
            if not isinstance(candidate, dict) or not _REQUIRED_FRIDAY_FIELDS.issubset(candidate): raise ValueError(f"Friday Review evidence record is invalid: {path.name}")
            records.append(candidate)
    if not records: raise ValueError("Friday Review evidence store contains no records")
    return records

def build_app() -> LeadAwareTonyApplication:
    app = build_base_app()
    if app.command_service is None: raise RuntimeError("Tony command service is not configured")
    records_root = Path(os.getenv("TONY_FRIDAY_REVIEW_RECORDS_ROOT", str(REPOSITORY_ROOT / ".runtime" / "executive-review-records")))
    workspace_id = os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip() or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip() or "narratiive"
    lead_path = Path(os.getenv("TONY_INBOUND_LEADS_PATH", str(REPOSITORY_ROOT / ".runtime" / "inbound-leads.json"))).resolve()
    lead_store = FileInboundLeadStore(lead_path); authoritative_lead_loader = build_authoritative_lead_loader(lead_store)
    executive_service = TonyExecutiveCommandService(app.command_service, brief_archive=app.brief_archive, friday_record_loader=lambda: load_friday_review_records(records_root), workspace_id=workspace_id, inbound_lead_loader=authoritative_lead_loader)
    capability_service = TonyCapabilityCommandService(executive_service)
    commercial_watch_service = TonyCommercialWatchCommandService(capability_service, store_path=Path(os.getenv("TONY_COMMERCIAL_COMMITMENTS_PATH", str(REPOSITORY_ROOT / ".runtime" / "commercial-commitments.json"))))
    agency_focus_service = TonyPersistentAgencyFocusCommandService(commercial_watch_service, store_path=Path(os.getenv("TONY_AGENCY_FOCUS_CONTEXT_PATH", str(REPOSITORY_ROOT / ".runtime" / "agency-focus-context.json"))))
    outcome_service = TonyOutcomeAccountabilityCommandService(agency_focus_service, store_path=Path(os.getenv("TONY_EXECUTIVE_OUTCOMES_PATH", str(REPOSITORY_ROOT / ".runtime" / "executive-outcomes.json"))))
    outcome_evidence_service = TonyOutcomeEvidenceCommandService(outcome_service)
    executive_learning_path = Path(os.getenv("TONY_EXECUTIVE_LEARNING_PATH", str(REPOSITORY_ROOT / ".runtime" / "executive-learning.json")))
    learning_service = TonyExecutiveLearningCommandService(outcome_evidence_service, store_path=executive_learning_path)
    adaptive_service = TonyAdaptiveResponseCommandService(learning_service, learning_store_path=executive_learning_path)
    memory_service = TonyMemoryCommandService(adaptive_service, ExecutiveMemoryStore(Path(os.getenv("TONY_EXECUTIVE_MEMORY_PATH", str(REPOSITORY_ROOT / ".runtime" / "executive-memory.jsonl")))), agency_id=workspace_id)
    live_dispatchers = build_http_dispatchers()
    dispatch_service = TonyCommercialAutonomousJudgementCommandService(memory_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_AUTONOMOUS_RESULT_CONTEXT_PATH", str(REPOSITORY_ROOT / ".runtime" / "autonomous-result-context.json"))))
    def accept_verified_commercial_result(worker: str, dispatch: dict[str, Any], evidence: dict[str, Any], executive_result: str) -> dict[str, Any]:
        verified, reason = dispatch_service._verify_evidence(dispatch, evidence)
        if not verified: raise ValueError(f"returned evidence is not verified: {reason}")
        context: dict[str, Any] = {"worker": worker, "dispatch": dict(dispatch), "evidence": dict(evidence), "executive_result": executive_result, "verified_at": dispatch_service._now().isoformat()}
        if not dispatch_service._enrich_context(context): raise ValueError("verified result is not recognised as a commercial judgement context")
        dispatch_service._last_verified_result = context; dispatch_service._persist_context(context); return dict(context)
    post_send_sync_service = TonyPostSendNotionSyncCommandService(dispatch_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_POST_SEND_NOTION_SYNC_PATH", str(REPOSITORY_ROOT / ".runtime" / "post-send-notion-sync.json"))))
    followup_service = TonyCommercialFollowupCommandService(post_send_sync_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_COMMERCIAL_FOLLOWUP_PATH", str(REPOSITORY_ROOT / ".runtime" / "commercial-followup.json"))))
    meeting_reply_service = TonyMeetingReplyPreparationCommandService(followup_service, dispatchers=live_dispatchers, verified_result_sink=accept_verified_commercial_result)
    meeting_booking_service = TonyConfirmedMeetingBookingCommandService(meeting_reply_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_MEETING_BOOKING_PATH", str(REPOSITORY_ROOT / ".runtime" / "meeting-booking.json"))))
    booking_sync_service = TonyPostBookingNotionSyncCommandService(meeting_booking_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_POST_BOOKING_NOTION_SYNC_PATH", str(REPOSITORY_ROOT / ".runtime" / "post-booking-notion-sync.json"))))
    discovery_outcome_service = TonyDiscoveryOutcomeTrackingCommandService(booking_sync_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_DISCOVERY_OUTCOME_TRACKING_PATH", str(REPOSITORY_ROOT / ".runtime" / "discovery-outcome-tracking.json"))))
    post_discovery_service = TonyPostDiscoveryCommercialCommandService(discovery_outcome_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_POST_DISCOVERY_COMMERCIAL_PATH", str(REPOSITORY_ROOT / ".runtime" / "post-discovery-commercial.json"))))
    proposal_execution_service = TonyPostDiscoveryProposalExecutionCommandService(post_discovery_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_POST_DISCOVERY_PROPOSAL_EXECUTION_PATH", str(REPOSITORY_ROOT / ".runtime" / "post-discovery-proposal-execution.json"))))
    proposal_outcome_service = TonyProposalOutcomeTrackingCommandService(proposal_execution_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_PROPOSAL_OUTCOME_TRACKING_PATH", str(REPOSITORY_ROOT / ".runtime" / "proposal-outcome-tracking.json"))))
    commercial_close_service = TonyCommercialCloseCommandService(proposal_outcome_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_COMMERCIAL_CLOSE_PATH", str(REPOSITORY_ROOT / ".runtime" / "commercial-close.json"))))
    delivery_bootstrap_service = TonyDeliveryBootstrapCommandService(commercial_close_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_DELIVERY_BOOTSTRAP_PATH", str(REPOSITORY_ROOT / ".runtime" / "delivery-bootstrap.json"))))
    drive_workspace_service = TonyDriveDeliveryWorkspaceCommandService(delivery_bootstrap_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_DRIVE_DELIVERY_WORKSPACE_PATH", str(REPOSITORY_ROOT / ".runtime" / "drive-delivery-workspace.json"))))
    delivery_commissioning_service = TonyDeliveryCommissioningCommandService(drive_workspace_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_DELIVERY_COMMISSIONING_PATH", str(REPOSITORY_ROOT / ".runtime" / "delivery-commissioning.json"))))
    delivery_blueprint_review_service = TonyDeliveryBlueprintReviewCommandService(delivery_commissioning_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_DELIVERY_BLUEPRINT_REVIEW_PATH", str(REPOSITORY_ROOT / ".runtime" / "delivery-blueprint-review.json"))))
    execution_status_service = TonyVerifiedExecutionStatusCommandService(delivery_blueprint_review_service)
    app.command_service = TonyTerminologyCommandService(execution_status_service)
    return LeadAwareTonyApplication(app, lead_store)

def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1"); port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server: print(f"Tony bridge listening on http://{host}:{port}"); server.serve_forever()

if __name__ == "__main__": main()
