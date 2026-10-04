from __future__ import annotations

import json
import os
import shlex
import hashlib
import hmac
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Mapping
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from openclaw.tony_agent_gateway import TonyAgentGateway, TonyAgentGatewayError, build_gateway
from openclaw.tony_http_bridge import (
    TonyHTTPBridge,
    TonyRuntimeComposition,
    build_app as build_base_app,
)
from openclaw.mission_control_web import MissionControlWebApplication
from runtime.executive_memory import ExecutiveMemoryStore
from runtime.executive_visibility import ExecutiveVisibilityPolicy
from runtime.execution_journal import ExecutionJournal
from runtime.campaign_engine import CampaignIdentity
from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.lead_attention import LeadAttentionService
from runtime.media_control import (
    CreativePlatformMapping,
    MediaConfigurationError,
    MediaControlError,
    MediaControlService,
    MediaProvider,
    MediaProviderError,
    ProviderObjectMapping,
)
from runtime.media_provider_transports import build_configured_media_adapters
from runtime.mission_control_operator import OperatorMissionControlProjector
from runtime.meta_oauth import (
    META_PERMISSION_NAMES,
    META_REDIRECT_URI,
    MetaOAuthError,
    MetaOAuthService,
)
from runtime.tiktok_oauth import (
    TIKTOK_PERMISSION_NAMES,
    TIKTOK_REDIRECT_URI,
    TikTokOAuthError,
    TikTokOAuthService,
)
from runtime.notion_leads import build_authoritative_lead_loader
from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_blueprint_client_delivery import TonyBlueprintClientDeliveryCommandService
from runtime.tony_blueprint_client_feedback import TonyBlueprintClientFeedbackCommandService
from runtime.tony_blueprint_delivery_notion_sync import TonyBlueprintDeliveryNotionSyncCommandService
from runtime.tony_blueprint_lite_inbound import (
    BlueprintLiteWebsiteResearch,
    FileBlueprintLitePreparationStore,
    TonyInboundBlueprintLiteService,
)
from runtime.tony_blueprint_revision_cycle import TonyBlueprintRevisionCycleCommandService
from runtime.tony_blueprint_revision_persistence import TonyBlueprintRevisionPersistenceCommandService
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
from runtime.campaign_learning_coordinator import CampaignLearningCoordinator
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
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_conversation_work import FileConversationWorkStore, TonyConversationIngress
from openclaw.telegram_output_policy import protect_telegram_output

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

_WORKFLOW_DECISION_TARGET = re.compile(
    r"\b(?:artefact|artifact|blueprint(?:\s+lite)?|strategy\s+thesis|research\s+report|campaign\s+world|"
    r"creative(?:\s+director(?:'s|’s))?\s+bible|proposal|version|current\s+work)\b",
    re.IGNORECASE,
)
_NEGATED_WORKFLOW_DECISION = re.compile(
    r"\b(?:do\s+not|don't|dont|not|never)\s+(?:explicitly\s+)?(?:approve|reject|revise)\b",
    re.IGNORECASE,
)
_QUESTION_WORKFLOW_DECISION = re.compile(r"^\s*(?:can|could|should|would|may)\s+(?:i|we)\b", re.IGNORECASE)


def has_explicit_workflow_decision_intent(operation: str, instruction: str) -> bool:
    """Recognise only an explicit artefact decision, never general progress language."""

    decision = operation.strip().casefold().replace("-", "_")
    text = str(instruction or "")
    if decision not in {"approve", "reject", "request_revision"} or not text.strip():
        return False
    if not _WORKFLOW_DECISION_TARGET.search(text):
        return False
    if _NEGATED_WORKFLOW_DECISION.search(text) or _QUESTION_WORKFLOW_DECISION.search(text):
        return False
    if decision == "approve":
        return bool(re.search(r"(?:^|[.!?]\s*|\b(?:i|we)\s+)(?:explicitly\s+)?approve\b", text, re.IGNORECASE))
    if decision == "reject":
        return bool(re.search(r"(?:^|[.!?]\s*|\b(?:i|we)\s+)(?:explicitly\s+)?reject\b", text, re.IGNORECASE))
    return bool(
        re.search(
            r"(?:^|[.!?]\s*)(?:please\s+)?revise\b|\b(?:i|we)\s+(?:explicitly\s+)?(?:request|require)\s+(?:a\s+)?revision\b",
            text,
            re.IGNORECASE,
        )
    )


def workflow_decision_proof_material(
    *, run_id: str, operation: str, reference: str, approval_token: str, instruction: str
) -> bytes:
    values = (
        "narratiive-workflow-decision-v1",
        run_id,
        operation.strip().casefold().replace("-", "_"),
        reference,
        approval_token,
        instruction,
    )
    return "\0".join(values).encode("utf-8")


def verify_workflow_decision_proof(
    secret: str,
    *,
    run_id: str,
    operation: str,
    reference: str,
    approval_token: str,
    instruction: str,
    proof: str,
) -> bool:
    if not secret or not run_id or not proof:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        workflow_decision_proof_material(
            run_id=run_id,
            operation=operation,
            reference=reference,
            approval_token=approval_token,
            instruction=instruction,
        ),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, proof)


def build_runtime_lead_loader(
    lead_store: FileInboundLeadStore,
    env: Mapping[str, str] | None = None,
) -> Callable[[], tuple[InboundLead, ...]]:
    """Select Tony's lead source explicitly.

    Production remains Notion-authoritative.  Isolated acceptance runtimes may
    opt into their own local inbound projection so a synthetic lead never has
    to be written to the live Notion workspace merely to be visible to Tony.
    Unknown modes fail closed during startup.
    """
    active_env = os.environ if env is None else env
    mode = str(active_env.get("TONY_INBOUND_LEAD_SOURCE") or "notion").strip().casefold()
    if mode == "notion":
        return build_authoritative_lead_loader(lead_store, env=active_env)
    if mode == "local_projection":
        return lead_store.read
    raise ValueError("TONY_INBOUND_LEAD_SOURCE must be 'notion' or 'local_projection'")


class ThreadingTonyServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
_REQUIRED_FRIDAY_FIELDS = {"record_id", "occurred_at", "record_type", "summary", "evidence", "workspace_id"}


class LeadAwareTonyApplication:
    """Live HTTP boundary: OpenClaw owns conversation; Narratiive owns explicit commands and consequences."""

    def __init__(
        self,
        base: TonyHTTPBridge,
        lead_store: FileInboundLeadStore,
        *,
        agent_gateway: TonyAgentGateway | None = None,
        blueprint_lite_service: TonyInboundBlueprintLiteService | None = None,
        workflow_command_service: TonyWorkflowCommandService | None = None,
        authorised_principal_id: str = "",
        attention_service: LeadAttentionService | None = None,
        conversation_ingress: TonyConversationIngress | None = None,
        media_control: MediaControlService | None = None,
        tiktok_oauth: TikTokOAuthService | None = None,
        meta_oauth: MetaOAuthService | None = None,
        mission_control_web: MissionControlWebApplication | None = None,
    ) -> None:
        self.base = base
        self.lead_store = lead_store
        self.agent_gateway = agent_gateway or build_gateway()
        self.blueprint_lite_service = blueprint_lite_service
        self.workflow_command_service = workflow_command_service
        self.authorised_principal_id = authorised_principal_id.strip()
        self.attention_service = attention_service
        self.conversation_ingress = conversation_ingress
        self.media_control = media_control
        self.tiktok_oauth = tiktok_oauth
        self.meta_oauth = meta_oauth
        self.mission_control_web = mission_control_web

    def __getattr__(self, name: str):
        return getattr(self.base, name)

    def __call__(self, environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "")).upper()
        path = str(environ.get("PATH_INFO", "/")) or "/"
        if path.startswith("/mission-control") and self.mission_control_web is not None:
            response = self.mission_control_web.handle(environ, start_response)
            if response is not None:
                return response
        if method == "POST" and path == "/leads/ingest":
            return self._ingest(environ, start_response)
        if method == "POST" and path == "/telegram/inbound":
            return self._telegram_inbound(environ, start_response)
        if method == "POST" and path == "/workflow/control":
            return self._workflow_control(environ, start_response)
        if method == "POST" and path == "/attention/control":
            return self._attention_control(environ, start_response)
        if method == "POST" and path == "/media/sync":
            return self._media_sync(environ, start_response)
        if method == "POST" and path == "/media/monitor":
            return self._media_monitor(environ, start_response)
        if method == "POST" and path == "/oauth/tiktok/start":
            return self._tiktok_oauth_start(environ, start_response)
        if method == "POST" and path == "/oauth/tiktok/callback":
            return self._tiktok_oauth_callback(environ, start_response)
        if method == "POST" and path == "/oauth/meta/start":
            return self._meta_oauth_start(environ, start_response)
        if method == "POST" and path == "/oauth/meta/callback":
            return self._meta_oauth_callback(environ, start_response)
        return self.base(environ, start_response)

    @staticmethod
    def _is_loopback(environ) -> bool:
        return str(environ.get("REMOTE_ADDR", "")).strip().casefold() in {"127.0.0.1", "::1", "localhost"}

    def _authorize(self, environ, start_response, *, allow_loopback: bool = False):
        if allow_loopback and self._is_loopback(environ):
            return None
        if not self.base.bridge_token:
            return None
        if str(environ.get("HTTP_AUTHORIZATION", "")) == f"Bearer {self.base.bridge_token}":
            return None
        return self._respond(start_response, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": {"code": "unauthorized", "message": "Invalid bridge token"}})

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
            if TonyAgentGateway.is_system_command(text):
                if self.workflow_command_service is not None and self.workflow_command_service.supports(text):
                    supplied_principal = str(request.get("principal_id") or "").strip()
                    principal = supplied_principal if supplied_principal == self.authorised_principal_id else ""
                    response = self.workflow_command_service.execute(text, (), principal_id=principal)
                    status = HTTPStatus.OK
                    payload = {
                        "ok": response.status != "error",
                        "reply": protect_telegram_output(response.message),
                        "message": protect_telegram_output(response.message),
                        **response.to_dict(),
                    }
                else:
                    status, payload = self.base._handle_telegram_command(text)
            else:
                if self.conversation_ingress is not None and self.conversation_ingress.requires_durable_work(text):
                    accepted = self.conversation_ingress.accept(request, text)
                    reply = protect_telegram_output(accepted.acknowledgement)
                    status = HTTPStatus.OK
                    payload = {
                        "ok": True,
                        "command": "conversation",
                        "status": "accepted",
                        "reply": reply,
                        "message": reply,
                        "data": {
                            "runtime": "narratiive_durable_work",
                            "work_id": accepted.work_id,
                            "replay": accepted.replay,
                            "external_action_taken": False,
                        },
                    }
                    return self._respond(start_response, status, payload)
                reply = self.agent_gateway.converse(text)
                if not reply.strip() or reply.strip().upper() == "NO_REPLY":
                    reply = (
                        "I’m here, but I don’t have a verified update I can stand behind yet. "
                        "I’m checking the persisted work rather than pretending it has progressed."
                    )
                reply = protect_telegram_output(reply)
                status = HTTPStatus.OK
                payload = {
                    "ok": True,
                    "command": "conversation",
                    "status": "ok",
                    "reply": reply,
                    "message": reply,
                    "data": {"runtime": "openclaw", "external_action_taken": False},
                }
        except TonyAgentGatewayError as exc:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "openclaw_conversation_unavailable", "message": str(exc)}})
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_telegram_message", "message": str(exc)}})
        return self._respond(start_response, status, payload)

    def _workflow_control(self, environ, start_response):
        denied = self._authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.workflow_command_service is None:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "workflow_control_unavailable", "message": "Workflow control is not configured"}})
        try:
            request = self._read_json(environ)
            operation = str(request.get("operation") or "").strip().casefold().replace("_", "-")
            commands = {
                "status": "workflow",
                "current-work": "work",
                "approvals": "approvals",
                "blockers": "blockers",
                "latest-artifact": "artefact",
                "artifact-detail": "artifact-detail",
                "action-preview": "action-preview",
                "execute-action": "execute-action",
                "proposed-next-action": "proposed",
                "approve": "approve",
                "reject": "reject",
                "request-revision": "reject",
                "continue": "continue",
                "resume": "resume",
                "recover": "recover",
                "projection": "projection",
                "sync-notion": "sync-notion",
                "additional-research": "research",
                "deliver-internal-review": "deliver-review",
                "commission": "commission",
                "client-portfolio": "campaigns",
                "campaign-learning": "learning",
                "campaign-learning-queue": "learning-queue",
                "sync-campaign-learning": "sync-learning",
            }
            command_name = commands.get(operation)
            if command_name is None:
                raise ValueError("unsupported workflow operation")
            reference = str(request.get("reference") or "").strip()
            rationale = str(request.get("rationale") or "").strip()
            inputs = request.get("inputs")
            if inputs is not None and not isinstance(inputs, dict):
                raise ValueError("workflow inputs must be an object")
            if inputs and operation not in {
                "continue", "additional-research", "deliver-internal-review",
                "approve", "reject", "request-revision", "commission", "action-preview", "execute-action",
                "sync-campaign-learning",
            }:
                raise ValueError("workflow inputs are not accepted for this operation")
            if operation not in {"current-work", "approvals", "blockers", "recover", "client-portfolio", "campaign-learning-queue"} and not reference:
                raise ValueError("workflow reference is required")
            command = f"/{command_name}" + (f" {shlex.quote(reference)}" if reference else "")
            if rationale:
                command += f" because {shlex.quote(rationale)}"
            if operation in {"approve", "reject", "request-revision", "commission", "execute-action", "sync-campaign-learning"}:
                if request.get("source") != "openclaw_telegram_workflow_tool" or not self.authorised_principal_id:
                    raise ValueError("workflow decision requires the authorised Telegram principal")
                if operation in {"approve", "reject", "request-revision"}:
                    instruction = str((inputs or {}).get("approval_instruction") or "")
                    approval_token = str((inputs or {}).get("approval_token") or "").strip()
                    instruction_run_id = str((inputs or {}).get("approval_instruction_run_id") or "").strip()
                    instruction_proof = str((inputs or {}).get("approval_instruction_proof") or "").strip()
                    if not has_explicit_workflow_decision_intent(operation, instruction):
                        raise ValueError(
                            "workflow artefact decision requires explicit approve, reject, or revision intent naming the artefact"
                        )
                    if not verify_workflow_decision_proof(
                        str(self.base.bridge_token or ""),
                        run_id=instruction_run_id,
                        operation=operation,
                        reference=reference,
                        approval_token=approval_token,
                        instruction=instruction,
                        proof=instruction_proof,
                    ):
                        raise ValueError("workflow artefact decision lacks verified verbatim current-human instruction provenance")
                    inputs["approval_decision_evidence"] = {
                        "human_instruction": instruction,
                        "human_instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
                        "turn_run_id": instruction_run_id,
                        "verbatim_current_human_instruction_verified": True,
                        "explicit_decision_intent": operation.replace("-", "_"),
                    }
                principal = (
                    f"matt:{self.authorised_principal_id}"
                    if operation == "sync-campaign-learning"
                    else self.authorised_principal_id
                )
            elif operation == "sync-notion" and request.get("approval_granted") is True:
                principal = "openclaw:native-approval"
            else:
                principal = ""
            response = self.workflow_command_service.execute(
                command,
                (),
                principal_id=principal,
                inputs=inputs,
            )
            payload = {
                "ok": response.status != "error",
                "reply": response.message[:3500],
                "message": response.message[:3500],
                **response.to_dict(),
            }
            return self._respond(start_response, HTTPStatus.OK, payload)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_workflow_control", "message": str(exc)}})

    def _attention_control(self, environ, start_response):
        denied = self._authorize(environ, start_response)
        if denied is not None: return denied
        if self.attention_service is None: return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "attention_unavailable", "message": "Attention control is not configured"}})
        try:
            request = self._read_json(environ); operation = str(request.get("operation") or "").casefold().replace("-", "_"); actor = str(request.get("actor") or "openclaw"); reason = str(request.get("reason") or "")
            if operation in {"show", "list"}: result = {"ok": True, "leads": [x.to_dict() for x in self.attention_service.list(str(request.get("scope") or "visible"))], "external_action_taken": False}
            elif operation in {"archive_safe_tests", "suppress_safe_tests"}: result = self.attention_service.batch_safe("archived" if operation.startswith("archive") else "suppressed", reason, actor)
            else:
                reference = str(request.get("reference") or "").strip()
                if not reference: raise ValueError("reference is required")
                mapping = {"ignore": "suppressed", "suppress": "suppressed", "mark_test": "test", "archive": "archived", "restore": "active", "watch": "watching"}
                result = self.attention_service.mutate(reference, mapping.get(operation, operation), reason, actor)
            return self._respond(start_response, HTTPStatus.OK, {**result, "reply": "Attention state updated." if result.get("ok") else "No attention state changed."})
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_attention_control", "message": str(exc)}})

    def _media_sync(self, environ, start_response):
        """Authenticated, read-only performance ingestion boundary for n8n."""
        if not str(self.base.bridge_token or "").strip():
            return self._respond(
                start_response,
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "ok": False,
                    "error": {
                        "code": "media_sync_auth_unavailable",
                        "message": "Media sync requires a configured bridge token",
                    },
                },
            )

        denied = self._authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.media_control is None:
            return self._respond(
                start_response,
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": {"code": "media_control_unavailable", "message": "Media control is not configured"}},
            )
        try:
            request = self._read_json(environ)
            identity_value = request.get("identity")
            mapping_value = request.get("provider_mapping")
            if not isinstance(identity_value, dict):
                raise ValueError("identity must be an object")
            if not isinstance(mapping_value, dict):
                raise ValueError("provider_mapping must be an object")
            identity = CampaignIdentity(
                workspace_id=str(identity_value.get("workspace_id") or "").strip(),
                client_id=str(identity_value.get("client_id") or "").strip(),
                brand_id=str(identity_value.get("brand_id") or "").strip(),
                market_ids=self._string_tuple(identity_value.get("market_ids"), "identity.market_ids"),
                product_ids=self._string_tuple(identity_value.get("product_ids"), "identity.product_ids"),
                campaign_id=str(identity_value.get("campaign_id") or "").strip(),
            )
            provider = MediaProvider(str(mapping_value.get("provider") or "").strip().casefold())
            provider_mapping = ProviderObjectMapping(
                provider=provider,
                account_id=str(mapping_value.get("account_id") or "").strip(),
                campaign_id=str(mapping_value.get("campaign_id") or "").strip(),
                ad_group_ids=self._optional_string_tuple(mapping_value.get("ad_group_ids"), "provider_mapping.ad_group_ids"),
                ad_ids=self._optional_string_tuple(mapping_value.get("ad_ids"), "provider_mapping.ad_ids"),
                creative_ids=self._optional_string_tuple(mapping_value.get("creative_ids"), "provider_mapping.creative_ids"),
            )
            creative_values = request.get("creative_mappings", [])
            if not isinstance(creative_values, list):
                raise ValueError("creative_mappings must be an array")
            creative_mappings = tuple(
                self._creative_mapping(value, provider, index)
                for index, value in enumerate(creative_values)
            )
            snapshot = self.media_control.ingest(
                identity=identity,
                provider_mapping=provider_mapping,
                period_start=self._required_string(request, "period_start"),
                period_end=self._required_string(request, "period_end"),
                request_id=self._required_string(request, "request_id"),
                tony_request=self._required_string(request, "tony_request"),
                creative_mappings=creative_mappings,
            )
            recommendations = self.media_control.analyse((snapshot,))
            return self._respond(
                start_response,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "status": "performance_ingested",
                    "snapshot": snapshot.to_dict(),
                    "recommendations": [item.to_dict() for item in recommendations],
                    "external_action_taken": False,
                    "publication_authorised": False,
                    "media_spend_authorised": False,
                },
            )
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, MediaControlError) as exc:
            unavailable = isinstance(exc, (MediaConfigurationError, MediaProviderError))
            status = HTTPStatus.SERVICE_UNAVAILABLE if unavailable else HTTPStatus.BAD_REQUEST
            code = "media_sync_unavailable" if unavailable else "invalid_media_sync"
            return self._respond(start_response, status, {"ok": False, "error": {"code": code, "message": str(exc)}})
        except Exception:
            return self._respond(
                start_response,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": {"code": "media_sync_failed", "message": "Media performance ingestion failed closed"}},
            )

    def _media_monitor(self, environ, start_response):
        """Authenticated scheduled media analysis; persists evidence but takes no external action."""

        denied = self._authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.media_control is None:
            return self._respond(
                start_response,
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": {"code": "media_control_unavailable", "message": "Media control is not configured"}},
            )
        try:
            request = self._read_json(environ)
            report = self.media_control.persist_monitoring_report(
                cadence=self._required_string(request, "cadence"),
                request_id=self._required_string(request, "request_id"),
                query=str(request.get("query") or "").strip(),
            )
            return self._respond(
                start_response,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "status": report["status"],
                    "report": report,
                    "external_action_taken": False,
                    "publication_authorised": False,
                    "media_spend_authorised": False,
                },
            )
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, MediaControlError) as exc:
            return self._respond(
                start_response,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_media_monitor", "message": str(exc)}},
            )
        except Exception:
            return self._respond(
                start_response,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": {"code": "media_monitor_failed", "message": "Media monitoring failed closed"}},
            )

    def _tiktok_oauth_start(self, environ, start_response):
        denied = self._oauth_authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.tiktok_oauth is None:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "tiktok_oauth_unavailable", "message": "TikTok OAuth is not configured"}})
        try:
            url = self.tiktok_oauth.authorization_url()
        except TikTokOAuthError as exc:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "tiktok_oauth_unavailable", "message": str(exc)}})
        return self._respond(start_response, HTTPStatus.OK, {
            "ok": True,
            "authorization_url": url,
            "redirect_uri": TIKTOK_REDIRECT_URI,
            "permissions": list(TIKTOK_PERMISSION_NAMES),
            "read_only": True,
            "external_action_taken": False,
        })

    def _tiktok_oauth_callback(self, environ, start_response):
        denied = self._oauth_authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.tiktok_oauth is None:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "tiktok_oauth_unavailable", "message": "TikTok OAuth is not configured"}})
        try:
            request = self._read_json(environ)
            provider_code = str(request.get("provider_code") or "0").strip()
            if provider_code not in {"", "0"}:
                raise TikTokOAuthError("TikTok advertiser authorisation was not approved")
            result = self.tiktok_oauth.exchange(
                state=str(request.get("state") or ""),
                auth_code=str(request.get("auth_code") or ""),
            )
        except (TikTokOAuthError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "tiktok_oauth_failed", "message": str(exc)}})
        return self._respond(start_response, HTTPStatus.OK, {
            "ok": True,
            "status": "tiktok_credentials_stored",
            "authorised_advertiser_ids": list(result.advertiser_ids),
            "account_selection_required": len(result.advertiser_ids) != 1,
            "granted_scopes": list(result.granted_scopes),
            "provider_capabilities": list(result.provider_capabilities),
            "read_only": True,
            "runtime_mutation_authority": False,
            "external_media_write_performed": False,
        })

    def _oauth_authorize(self, environ, start_response):
        if not str(self.base.bridge_token or "").strip():
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "oauth_auth_unavailable", "message": "OAuth requires a configured bridge token"}})
        return self._authorize(environ, start_response)

    def _meta_oauth_start(self, environ, start_response):
        denied = self._oauth_authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.meta_oauth is None:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "meta_oauth_unavailable", "message": "Meta OAuth is not configured"}})
        try:
            url = self.meta_oauth.authorization_url()
        except MetaOAuthError as exc:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "meta_oauth_unavailable", "message": str(exc)}})
        return self._respond(start_response, HTTPStatus.OK, {
            "ok": True,
            "authorization_url": url,
            "redirect_uri": META_REDIRECT_URI,
            "permissions": list(META_PERMISSION_NAMES),
            "read_only": True,
            "external_action_taken": False,
        })

    def _meta_oauth_callback(self, environ, start_response):
        denied = self._oauth_authorize(environ, start_response)
        if denied is not None:
            return denied
        if self.meta_oauth is None:
            return self._respond(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": {"code": "meta_oauth_unavailable", "message": "Meta OAuth is not configured"}})
        try:
            request = self._read_json(environ)
            if str(request.get("error") or "").strip():
                raise MetaOAuthError("Meta advertising authorisation was not approved")
            result = self.meta_oauth.exchange(
                state=str(request.get("state") or ""),
                code=str(request.get("code") or ""),
            )
        except (MetaOAuthError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "meta_oauth_failed", "message": str(exc)}})
        return self._respond(start_response, HTTPStatus.OK, {
            "ok": True,
            "status": "meta_credentials_stored",
            "authorised_ad_account_ids": list(result.account_ids),
            "account_selection_required": len(result.account_ids) != 1,
            "granted_scopes": list(result.granted_scopes),
            "provider_capabilities": list(result.provider_capabilities),
            "read_only": True,
            "runtime_mutation_authority": False,
            "external_media_write_performed": False,
        })

    @staticmethod
    def _required_string(value: dict[str, Any], field: str) -> str:
        result = str(value.get(field) or "").strip()
        if not result:
            raise ValueError(f"{field} is required")
        return result

    @staticmethod
    def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not value:
            raise ValueError(f"{field} must be a non-empty array")
        result = tuple(str(item).strip() for item in value)
        if any(not item for item in result):
            raise ValueError(f"{field} must contain non-empty strings")
        return result

    @staticmethod
    def _optional_string_tuple(value: Any, field: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ValueError(f"{field} must be an array")
        result = tuple(str(item).strip() for item in value)
        if any(not item for item in result):
            raise ValueError(f"{field} must contain non-empty strings")
        return result

    @classmethod
    def _creative_mapping(cls, value: Any, provider: MediaProvider, index: int) -> CreativePlatformMapping:
        if not isinstance(value, dict):
            raise ValueError(f"creative_mappings[{index}] must be an object")
        creative_provider = MediaProvider(str(value.get("provider") or "").strip().casefold())
        if creative_provider is not provider:
            raise ValueError(f"creative_mappings[{index}].provider must match provider_mapping.provider")
        return CreativePlatformMapping(
            narratiive_asset_id=cls._required_string(value, "narratiive_asset_id"),
            campaign_world_id=cls._required_string(value, "campaign_world_id"),
            creative_territory=cls._required_string(value, "creative_territory"),
            format=cls._required_string(value, "format"),
            hook=str(value.get("hook") or "").strip(),
            message=str(value.get("message") or "").strip(),
            audience=str(value.get("audience") or "").strip(),
            provider=creative_provider,
            placement=str(value.get("placement") or "").strip(),
            provider_creative_ids=cls._optional_string_tuple(value.get("provider_creative_ids"), f"creative_mappings[{index}].provider_creative_ids"),
            provider_ad_ids=cls._optional_string_tuple(value.get("provider_ad_ids"), f"creative_mappings[{index}].provider_ad_ids"),
        )

    def _ingest(self, environ, start_response):
        denied = self._authorize(environ, start_response)
        if denied is not None:
            return denied
        try:
            request = self._read_json(environ)
            payload = request.get("lead") if isinstance(request.get("lead"), dict) else request
            diagnostic = request.get("diagnostic") if isinstance(request.get("diagnostic"), dict) else {}
            source_submission_id = str(
                diagnostic.get("lead_id")
                or diagnostic.get("leadId")
                or diagnostic.get("id")
                or ""
            ).strip()
            if source_submission_id:
                # Notion creates a fresh page id for every POST. The originating
                # form submission id is the durable business identity and keeps
                # retries from becoming separate Tony leads and preparation jobs.
                payload = dict(payload)
                payload["lead_id"] = source_submission_id
            lead = InboundLead.from_mapping(payload)
            self.lead_store.upsert(lead)
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "invalid_lead", "message": str(exc)}})
        except Exception:
            return self._respond(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": {"code": "lead_store_error", "message": "Tony could not persist inbound lead state"}})

        preparation = None
        if self.blueprint_lite_service is not None:
            try:
                preparation_payload = request if isinstance(request.get("lead"), dict) else payload
                preparation = self.blueprint_lite_service.enqueue_and_start(lead, preparation_payload)
            except Exception:
                preparation = {
                    "state": "blocked",
                    "lead_id": lead.lead_id,
                    "blocker": "blueprint_lite_orchestration_error",
                    "approval_required": False,
                    "external_action_taken": False,
                }

        response: dict[str, Any] = {
            "ok": True,
            "status": "lead_ingested",
            "lead_id": lead.lead_id,
            "contact": lead.contact,
            "source": lead.source,
        }
        if preparation is not None:
            response["preparation_status"] = preparation.get("state", "unknown")
            response["preparation"] = preparation
        return self._respond(start_response, HTTPStatus.OK, response)

    @staticmethod
    def _respond(start_response, status: HTTPStatus, payload: dict[str, Any]):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        start_response(f"{status.value} {status.phrase}", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]


def load_friday_review_records(root: Path) -> list[dict[str, Any]]:
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
    live_dispatchers = build_http_dispatchers()
    app = build_base_app(dispatchers=live_dispatchers)
    if app.command_service is None:
        raise RuntimeError("Tony command service is not configured")
    records_root = Path(os.getenv("TONY_FRIDAY_REVIEW_RECORDS_ROOT", str(REPOSITORY_ROOT / ".runtime" / "executive-review-records")))
    workspace_id = os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip() or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip() or "narratiive"
    lead_path = Path(os.getenv("TONY_INBOUND_LEADS_PATH", str(REPOSITORY_ROOT / ".runtime" / "inbound-leads.json"))).resolve()
    lead_store = FileInboundLeadStore(lead_path)
    attention_service = LeadAttentionService(lead_store, Path(os.getenv("TONY_LEAD_ATTENTION_EVENTS_PATH", str(REPOSITORY_ROOT / ".runtime" / "lead-attention-events.jsonl"))))
    authoritative_lead_loader = build_runtime_lead_loader(lead_store)
    visibility = ExecutiveVisibilityPolicy()
    executive_service = TonyExecutiveCommandService(
        app.command_service,
        brief_archive=app.brief_archive,
        friday_record_loader=lambda: load_friday_review_records(records_root),
        workspace_id=workspace_id,
        inbound_lead_loader=lambda: visibility.visible_leads(authoritative_lead_loader()),
    )
    capability_service = TonyCapabilityCommandService(executive_service)
    commercial_watch_service = TonyCommercialWatchCommandService(capability_service, store_path=Path(os.getenv("TONY_COMMERCIAL_COMMITMENTS_PATH", str(REPOSITORY_ROOT / ".runtime" / "commercial-commitments.json"))))
    agency_focus_service = TonyPersistentAgencyFocusCommandService(commercial_watch_service, store_path=Path(os.getenv("TONY_AGENCY_FOCUS_CONTEXT_PATH", str(REPOSITORY_ROOT / ".runtime" / "agency-focus-context.json"))))
    outcome_service = TonyOutcomeAccountabilityCommandService(agency_focus_service, store_path=Path(os.getenv("TONY_EXECUTIVE_OUTCOMES_PATH", str(REPOSITORY_ROOT / ".runtime" / "executive-outcomes.json"))))
    outcome_evidence_service = TonyOutcomeEvidenceCommandService(outcome_service)
    executive_learning_path = Path(os.getenv("TONY_EXECUTIVE_LEARNING_PATH", str(REPOSITORY_ROOT / ".runtime" / "executive-learning.json")))
    learning_service = TonyExecutiveLearningCommandService(outcome_evidence_service, store_path=executive_learning_path)
    adaptive_service = TonyAdaptiveResponseCommandService(learning_service, learning_store_path=executive_learning_path)
    memory_service = TonyMemoryCommandService(adaptive_service, ExecutiveMemoryStore(Path(os.getenv("TONY_EXECUTIVE_MEMORY_PATH", str(REPOSITORY_ROOT / ".runtime" / "executive-memory.jsonl")))), agency_id=workspace_id)
    workflow_runtime_root = Path(
        os.getenv("TONY_WORKFLOW_RUNTIME_ROOT", str(REPOSITORY_ROOT / ".runtime" / "workflow-runtime"))
    )
    blueprint_lite_service = TonyInboundBlueprintLiteService(
        FileBlueprintLitePreparationStore(
            Path(os.getenv("TONY_BLUEPRINT_LITE_PREPARATION_PATH", str(REPOSITORY_ROOT / ".runtime" / "blueprint-lite-preparation.json")))
        ),
        dispatchers=live_dispatchers,
        workflow_runtime_root=workflow_runtime_root,
        researcher=BlueprintLiteWebsiteResearch(workflow_runtime_root / "blueprint-lite-research"),
    )
    dispatch_service = TonyCommercialAutonomousJudgementCommandService(memory_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_AUTONOMOUS_RESULT_CONTEXT_PATH", str(REPOSITORY_ROOT / ".runtime" / "autonomous-result-context.json"))))

    def accept_verified_commercial_result(worker: str, dispatch: dict[str, Any], evidence: dict[str, Any], executive_result: str) -> dict[str, Any]:
        verified, reason = dispatch_service._verify_evidence(dispatch, evidence)
        if not verified:
            raise ValueError(f"returned evidence is not verified: {reason}")
        context: dict[str, Any] = {"worker": worker, "dispatch": dict(dispatch), "evidence": dict(evidence), "executive_result": executive_result, "verified_at": dispatch_service._now().isoformat()}
        if not dispatch_service._enrich_context(context):
            raise ValueError("verified result is not recognised as a commercial judgement context")
        dispatch_service._last_verified_result = context
        dispatch_service._persist_context(context)
        return dict(context)

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
    blueprint_client_delivery_service = TonyBlueprintClientDeliveryCommandService(delivery_blueprint_review_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_BLUEPRINT_CLIENT_DELIVERY_PATH", str(REPOSITORY_ROOT / ".runtime" / "blueprint-client-delivery.json"))))
    blueprint_delivery_notion_sync_service = TonyBlueprintDeliveryNotionSyncCommandService(blueprint_client_delivery_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_BLUEPRINT_DELIVERY_NOTION_SYNC_PATH", str(REPOSITORY_ROOT / ".runtime" / "blueprint-delivery-sync.json"))))
    blueprint_client_feedback_service = TonyBlueprintClientFeedbackCommandService(blueprint_delivery_notion_sync_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_BLUEPRINT_CLIENT_FEEDBACK_PATH", str(REPOSITORY_ROOT / ".runtime" / "blueprint-feedback.json"))))
    blueprint_revision_service = TonyBlueprintRevisionCycleCommandService(blueprint_client_feedback_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_BLUEPRINT_REVISION_CYCLE_PATH", str(REPOSITORY_ROOT / ".runtime" / "blueprint-revision.json"))))
    blueprint_revision_persistence_service = TonyBlueprintRevisionPersistenceCommandService(blueprint_revision_service, dispatchers=live_dispatchers, store_path=Path(os.getenv("TONY_BLUEPRINT_REVISION_PERSISTENCE_PATH", str(REPOSITORY_ROOT / ".runtime" / "blueprint-revision-persistence.json"))))
    execution_status_service = TonyVerifiedExecutionStatusCommandService(blueprint_revision_persistence_service)
    media_control = MediaControlService(
        build_configured_media_adapters(os.environ),
        ExecutionJournal(
            Path(
                os.getenv(
                    "TONY_MEDIA_CONTROL_STATE_ROOT",
                    str(REPOSITORY_ROOT / ".runtime" / "media-control"),
                )
            )
        ),
    )
    app.command_service = TonyTerminologyCommandService(
        execution_status_service,
        media_control=media_control,
    )
    composition = getattr(app, "runtime_composition", None)
    workflow_backend = (
        composition.workflow_backend
        if isinstance(composition, TonyRuntimeComposition)
        else FileWorkflowCommandBackend(
            workflow_runtime_root,
            dispatchers=live_dispatchers,
            workspace_id=workspace_id,
        )
    )
    workflow_command_service = TonyWorkflowCommandService(
        app.command_service,
        workflow_backend,
        campaign_learning=CampaignLearningCoordinator(
            Path(
                os.getenv(
                    "TONY_CAMPAIGN_LEARNING_ROOT",
                    str(REPOSITORY_ROOT / ".runtime" / "campaign-learning"),
                )
            ),
            media_control,
            notion_dispatcher=live_dispatchers.get("Notion"),
        ),
    )
    blueprint_lite_service.recover_pending()
    conversation_store = FileConversationWorkStore(
        Path(os.getenv("TONY_CONVERSATION_WORK_ROOT", str(REPOSITORY_ROOT / ".runtime" / "conversation-work"))).resolve()
    )
    conversation_ingress = TonyConversationIngress(conversation_store, workspace_id=workspace_id)
    operator_projector = OperatorMissionControlProjector(
        workflow_root=workflow_runtime_root,
        workflow_workspace_id=(
            composition.workflow_workspace_id
            if isinstance(composition, TonyRuntimeComposition)
            else workspace_id
        ),
    )

    def load_operator_snapshot() -> dict[str, Any]:
        system = (
            composition.mission_control_loader().to_dict()
            if isinstance(composition, TonyRuntimeComposition)
            else {"status": "unknown", "connections": []}
        )
        latest_provider_evidence: dict[str, Any] = {}
        try:
            for record in media_control.journal.read_all():
                metadata = record.metadata
                provider = str(metadata.get("provider") or "").casefold()
                if (
                    record.action == "media.provider_interaction"
                    and metadata.get("operation") == "certify_provider"
                    and provider in {"google", "meta", "tiktok"}
                ):
                    latest_provider_evidence[provider] = record
        except Exception:
            latest_provider_evidence = {}
        provider_labels = {"google": "Google Ads", "meta": "Meta Ads", "tiktok": "TikTok Ads"}
        for provider in ("google", "meta", "tiktok"):
            record = latest_provider_evidence.get(provider)
            verified = bool(
                record
                and record.status == "completed"
                and record.metadata.get("result") == "live_read_verified"
            )
            system.setdefault("connections", []).append(
                {
                    "name": provider_labels[provider],
                    "state": "healthy_live" if verified else "unknown",
                    "evidence": (
                        f"Successful live read recorded at {record.occurred_at}"
                        if verified
                        else "No successful live provider read is recorded in the execution journal."
                    ),
                    "last_checked_at": record.occurred_at if record else None,
                }
            )
        certification_reports = sorted(
            (REPOSITORY_ROOT / ".runtime" / "golden-path-certification").glob("*/report.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if certification_reports:
            try:
                report = json.loads(certification_reports[0].read_text(encoding="utf-8"))
                if report.get("status") == "PASS" and report.get("certification_id"):
                    system.setdefault("connections", []).append(
                        {
                            "name": "Golden Path",
                            "state": "connected",
                            "evidence": f"Certified: {report['certification_id']}",
                        }
                    )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
        return operator_projector.project(
            states=workflow_backend.list_states(),
            leads=lead_store.read(),
            system_snapshot=system,
        )

    mission_control_web = MissionControlWebApplication(
        load_operator_snapshot,
        workflow_root=workflow_runtime_root,
    )
    return LeadAwareTonyApplication(
        app,
        lead_store,
        agent_gateway=build_gateway(),
        blueprint_lite_service=blueprint_lite_service,
        workflow_command_service=workflow_command_service,
        authorised_principal_id=(
            f"telegram:{os.getenv('TONY_TELEGRAM_CHAT_ID', '').strip()}"
            if os.getenv("TONY_TELEGRAM_CHAT_ID", "").strip()
            else ""
        ),
        attention_service=attention_service,
        conversation_ingress=conversation_ingress,
        media_control=media_control,
        tiktok_oauth=TikTokOAuthService.from_environment(os.environ),
        meta_oauth=MetaOAuthService.from_environment(os.environ),
        mission_control_web=mission_control_web,
    )


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app(), server_class=ThreadingTonyServer) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
