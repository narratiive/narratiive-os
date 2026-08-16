from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]


class TonyPostSendNotionSyncCommandService:
    """Turn a verified commercial Gmail send into a controlled Notion state update.

    Gmail execution and Notion bookkeeping are deliberately separate consequential
    writes. A verified Gmail receipt prepares the exact authoritative lead update, but
    Tony does not mutate Notion until Matt approves that bounded record change. The
    pending update is durable across restarts and completed Gmail receipts are retained
    so a replay cannot create duplicate commercial-state writes.
    """

    _APPROVAL_MARKERS = {
        "do that",
        "do it",
        "go ahead",
        "go ahead with that",
        "update notion",
        "record it",
        "yes, do that",
        "yes do that",
    }

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._state = self._load_state()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending = self._state.get("pending")
        if isinstance(pending, dict) and normalized in self._APPROVAL_MARKERS:
            return self._execute_pending_sync(pending)

        response = self.command_service.execute(command, objects)
        return self._prepare_from_verified_gmail(response)

    def _prepare_from_verified_gmail(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        result = data.get("dispatch_result")
        handoff = data.get("execution_handoff")
        if not isinstance(result, dict) or not isinstance(handoff, dict):
            return response
        if str(result.get("worker") or "").strip().casefold() != "gmail":
            return response
        if str(result.get("status") or "").strip().casefold() != "verified":
            return response

        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        message_id = str(evidence.get("message_id") or "").strip()
        if not message_id:
            return response

        dispatch = handoff.get("dispatch") if isinstance(handoff.get("dispatch"), dict) else {}
        payload = dispatch.get("payload") if isinstance(dispatch.get("payload"), dict) else {}
        target = dispatch.get("target") if isinstance(dispatch.get("target"), dict) else {}
        if str(dispatch.get("execution_mode") or "") != "approval_gated_write":
            return response
        if str(payload.get("kind") or "") != "reviewed_outreach_email":
            return response
        if str(target.get("area") or "").strip().casefold() != "commercial":
            return response

        completed = set(str(item) for item in self._state.get("completed_gmail_receipts", ()) if str(item).strip())
        existing = self._state.get("pending") if isinstance(self._state.get("pending"), dict) else {}
        if message_id in completed or existing.get("gmail_message_id") == message_id:
            return response

        pending = {
            "gmail_message_id": message_id,
            "lead_id": str(target.get("lead_id") or "").strip(),
            "contact": str(target.get("contact") or "").strip(),
            "company": str(target.get("company") or "").strip(),
            "status": "Contacted",
            "prepared_at": self._now().isoformat(),
        }
        self._state["pending"] = pending
        self._persist_state()

        sync = {
            "state": "awaiting_approval",
            "worker": "Notion",
            "approval_required": True,
            "approval_scope": "post_send_commercial_state_sync",
            "gmail_message_id": message_id,
            "lead_id": pending["lead_id"],
            "contact": pending["contact"],
            "status": "Contacted",
            "external_action_taken": False,
        }
        data["commercial_state_sync"] = sync
        data["execution_status"] = "gmail_verified_notion_approval_required"
        label = pending["contact"] or pending["lead_id"] or "the lead"
        return CommandResponse(
            command=response.command,
            status=response.status,
            message=(
                response.message
                + f" Gmail execution is verified with receipt {message_id}. I have prepared the matching Notion update to mark {label} as Contacted, but I have not changed the commercial record yet. Say 'do that' to approve this exact record update."
            ),
            data=data,
        )

    def _execute_pending_sync(self, pending: dict[str, Any]) -> CommandResponse:
        handler = self.dispatchers.get("Notion")
        if handler is None:
            return CommandResponse(
                command="post_send_notion_sync",
                status="healthy",
                message=(
                    "The Gmail send is already verified, but I cannot update the authoritative Notion record because no live Notion dispatcher is configured. The update remains pending and nothing has been falsely marked as changed."
                ),
                data={
                    "execution_status": "notion_dispatcher_unavailable",
                    "commercial_state_sync": dict(pending),
                    "external_action_taken": False,
                },
            )

        dispatch = {
            "eligible": False,
            "state": "approved_pending_execution",
            "worker": "Notion",
            "instruction": (
                "Update the authoritative commercial lead record to Contacted only because the outbound Gmail send has verified execution evidence. Preserve the Gmail receipt on the record for auditability."
            ),
            "target": {
                "lead_id": str(pending.get("lead_id") or ""),
                "contact": str(pending.get("contact") or ""),
                "company": str(pending.get("company") or ""),
                "area": "commercial",
            },
            "execution_mode": "approval_gated_write",
            "expected_evidence": "verified Notion update with a page or record identifier",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "approval_granted": True,
            "approval_scope": "post_send_commercial_state_sync",
            "payload": {
                "kind": "confirmed_outreach_state_update",
                "status": "Contacted",
                "gmail_message_id": str(pending.get("gmail_message_id") or ""),
                "lead_id": str(pending.get("lead_id") or ""),
                "contact": str(pending.get("contact") or ""),
            },
        }

        try:
            evidence = handler(dict(dispatch))
        except Exception as exc:
            return CommandResponse(
                command="post_send_notion_sync",
                status="healthy",
                message=(
                    f"I attempted the approved Notion record update, but it did not return verified evidence: {exc}. The update remains pending."
                ),
                data={
                    "execution_status": "notion_sync_failed",
                    "commercial_state_sync": dict(pending),
                    "external_action_taken": False,
                },
            )

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return CommandResponse(
                command="post_send_notion_sync",
                status="healthy",
                message=(
                    f"I attempted the approved Notion record update, but the evidence was not strong enough to treat it as complete ({reason}). The update remains pending."
                ),
                data={
                    "execution_status": "notion_sync_unverified",
                    "commercial_state_sync": dict(pending),
                    "notion_evidence": evidence if isinstance(evidence, dict) else {},
                    "external_action_taken": False,
                },
            )

        gmail_message_id = str(pending.get("gmail_message_id") or "")
        completed = [str(item) for item in self._state.get("completed_gmail_receipts", ()) if str(item).strip()]
        if gmail_message_id and gmail_message_id not in completed:
            completed.append(gmail_message_id)
        self._state = {"pending": None, "completed_gmail_receipts": completed[-100:]}
        self._persist_state()
        notion_id = str(evidence.get("page_id") or evidence.get("record_id") or "").strip()
        return CommandResponse(
            command="post_send_notion_sync",
            status="healthy",
            message=(
                f"Confirmed. The authoritative Notion lead record is now updated to Contacted against verified Gmail receipt {gmail_message_id}"
                + (f" and Notion record {notion_id}." if notion_id else ".")
                + " The next commercial step is to monitor for a reply and keep the follow-up commitment active."
            ),
            data={
                "execution_status": "commercial_state_sync_verified",
                "gmail_message_id": gmail_message_id,
                "notion_receipt": notion_id,
                "notion_evidence": dict(evidence),
                "follow_up_commitment": {
                    "status": "pending",
                    "trigger": "3_business_days_after_verified_send",
                },
                "external_action_taken": True,
            },
        )

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"pending": None, "completed_gmail_receipts": []}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed_gmail_receipts": []}
        if not isinstance(payload, dict):
            return {"pending": None, "completed_gmail_receipts": []}
        pending = payload.get("pending") if isinstance(payload.get("pending"), dict) else None
        completed = payload.get("completed_gmail_receipts") if isinstance(payload.get("completed_gmail_receipts"), list) else []
        return {"pending": pending, "completed_gmail_receipts": completed}

    def _persist_state(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.store_path)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
