from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyPostDiscoveryProposalExecutionCommandService:
    """Review a prepared proposal, gate its send, then gate the Notion stage update."""

    SEND_APPROVALS = {
        "send it", "send that", "send this", "go ahead and send it", "go ahead and send that",
        "yes send it", "yes, send it",
    }
    NOTION_APPROVALS = {
        "do that", "do it", "go ahead", "update notion", "record it", "yes do that", "yes, do that",
    }

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending_notion = self.state.get("pending_notion") if isinstance(self.state.get("pending_notion"), dict) else None
        if pending_notion and normalized in self.NOTION_APPROVALS:
            return self._sync_notion(pending_notion)
        pending_send = self.state.get("pending_send") if isinstance(self.state.get("pending_send"), dict) else None
        if pending_send and normalized in self.SEND_APPROVALS:
            return self._send(pending_send)

        response = self.command_service.execute(command, objects)
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("execution_status") == "post_discovery_proposal_draft_ready":
            return self._review(response)
        return response

    def _review(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data)
        evidence = data.get("proposal_evidence") if isinstance(data.get("proposal_evidence"), dict) else {}
        context = data.get("post_discovery_commercial") if isinstance(data.get("post_discovery_commercial"), dict) else {}
        body = self._first_text(evidence, ("email_body", "proposal", "draft", "work_product", "content", "result"))
        subject = self._first_text(evidence, ("email_subject", "subject"))
        company = str(context.get("company") or "").strip()
        contact = str(context.get("contact") or "").strip()
        if not subject and company:
            subject = f"Proposal for {company}"
        words = len(body.split()) if body else 0
        folded = body.casefold()
        checks = {
            "proposal_present": bool(body),
            "proposal_substantive": 70 <= words <= 1200,
            "problem_present": any(term in folded for term in ("problem", "challenge", "need", "diagnos")),
            "scope_present": "scope" in folded,
            "outcomes_present": any(term in folded for term in ("outcome", "result", "impact")),
            "next_step_present": any(term in folded for term in ("next step", "next steps", "proceed", "review")),
            "no_false_execution_claim": not any(term in folded for term in ("proposal sent", "i sent", "we sent", "notion updated", "meeting booked")),
        }
        ready = all(checks.values()) and bool(subject)
        failed = [name.replace("_", " ") for name, passed in checks.items() if not passed]
        if not ready:
            data["execution_status"] = "post_discovery_proposal_revision_required"
            data["proposal_review"] = {"state": "revision_required", "checks": checks, "failed_checks": failed, "external_action_taken": False}
            return CommandResponse(
                response.command,
                response.status,
                response.message + " I reviewed the proposal and would not send it yet. It needs revision on: " + (", ".join(failed) or "the proposal quality requirements") + ". Nothing has been sent or changed in Notion.",
                data,
            )

        pending = {
            "lead_id": str(context.get("lead_id") or ""),
            "contact": contact,
            "company": company,
            "calendar_event_id": str(context.get("calendar_event_id") or ""),
            "subject": subject,
            "body": body,
        }
        self.state["pending_send"] = pending
        self._persist()
        data["execution_status"] = "post_discovery_proposal_ready_for_send_approval"
        data["proposal_review"] = {"state": "ready_for_send_approval", "checks": checks, "subject": subject, "approval_required": True, "external_action_taken": False}
        return CommandResponse(
            response.command,
            response.status,
            response.message + " I reviewed the proposal against the verified discovery context. It is substantive and ready for your final send approval. Nothing has been sent or changed in Notion. Say 'send it' to approve this exact proposal.",
            data,
        )

    def _send(self, pending: dict[str, Any]) -> CommandResponse:
        gmail = self.dispatchers.get("Gmail")
        if gmail is None:
            return CommandResponse("post_discovery_proposal", "healthy", "The reviewed proposal is approved for send, but no live Gmail dispatcher is configured. Nothing has been sent.", {"execution_status": "proposal_gmail_dispatcher_unavailable", "external_action_taken": False})
        dispatch = {
            "eligible": False,
            "state": "approved_pending_execution",
            "worker": "Gmail",
            "instruction": "Send the reviewed proposal exactly as supplied. Do not alter the subject or body and do not perform any other external action.",
            "target": {"lead_id": pending.get("lead_id", ""), "contact": pending.get("contact", ""), "company": pending.get("company", ""), "area": "commercial"},
            "execution_mode": "approval_gated_write",
            "expected_evidence": "verified Gmail send with message identifier",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "approval_granted": True,
            "approval_scope": "post_discovery_proposal_send",
            "payload": {"kind": "reviewed_post_discovery_proposal", "email_subject": pending.get("subject", ""), "email_body": pending.get("body", "")},
        }
        try:
            evidence = gmail(dict(dispatch))
        except Exception as exc:
            return CommandResponse("post_discovery_proposal", "healthy", f"The approved proposal send failed: {exc}. I am not treating it as sent.", {"execution_status": "proposal_send_failed", "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        message_id = str(evidence.get("message_id") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not message_id:
            return CommandResponse("post_discovery_proposal", "healthy", f"Gmail did not return enough evidence to prove the proposal was sent ({reason if not verified else 'missing message identifier'}). I am not treating it as sent.", {"execution_status": "proposal_send_unverified", "external_action_taken": False})
        notion_pending = {**dict(pending), "gmail_message_id": message_id}
        self.state["pending_send"] = None
        self.state["pending_notion"] = notion_pending
        self._persist()
        return CommandResponse(
            "post_discovery_proposal",
            "healthy",
            f"Confirmed. Gmail returned verified send evidence for the reviewed proposal with message {message_id}. I have prepared the matching Notion update to mark the opportunity Proposal sent, but I have not changed the record. Say 'do that' to approve that exact stage update.",
            {"execution_status": "proposal_send_verified_notion_approval_required", "gmail_message_id": message_id, "proposal_send_evidence": dict(evidence), "commercial_state_sync": {"state": "awaiting_approval", "status": "Proposal sent", **notion_pending}, "external_action_taken": True},
        )

    def _sync_notion(self, pending: dict[str, Any]) -> CommandResponse:
        notion = self.dispatchers.get("Notion")
        if notion is None:
            return CommandResponse("post_discovery_proposal", "healthy", "The proposal send is verified, but no live Notion dispatcher is configured. The Proposal sent stage update remains pending.", {"execution_status": "proposal_notion_dispatcher_unavailable", "external_action_taken": False})
        dispatch = {
            "eligible": False,
            "state": "approved_pending_execution",
            "worker": "Notion",
            "instruction": "Update the authoritative commercial record to Proposal sent because Gmail has verified the reviewed proposal send. Preserve the Gmail message identifier for auditability.",
            "target": {"lead_id": pending.get("lead_id", ""), "contact": pending.get("contact", ""), "company": pending.get("company", ""), "area": "commercial"},
            "execution_mode": "approval_gated_write",
            "expected_evidence": "verified Notion update with page or record identifier",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "approval_granted": True,
            "approval_scope": "post_discovery_proposal_state_sync",
            "payload": {"kind": "verified_proposal_sent_state_update", "status": "Proposal sent", "gmail_message_id": pending.get("gmail_message_id", ""), "calendar_event_id": pending.get("calendar_event_id", "")},
        }
        try:
            evidence = notion(dict(dispatch))
        except Exception as exc:
            return CommandResponse("post_discovery_proposal", "healthy", f"The approved Notion Proposal sent update failed: {exc}. It remains pending.", {"execution_status": "proposal_notion_sync_failed", "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        notion_id = str(evidence.get("page_id") or evidence.get("record_id") or "").strip() if isinstance(evidence, dict) else ""
        if not verified or not notion_id:
            return CommandResponse("post_discovery_proposal", "healthy", f"Notion did not return enough evidence to prove the Proposal sent update ({reason if not verified else 'missing record identifier'}). It remains pending.", {"execution_status": "proposal_notion_sync_unverified", "external_action_taken": False})
        self.state["pending_notion"] = None
        self.state["last_completed"] = {**dict(pending), "notion_receipt": notion_id}
        self._persist()
        return CommandResponse(
            "post_discovery_proposal",
            "healthy",
            f"Confirmed. Notion is now Proposal sent for this opportunity, backed by Gmail message {pending.get('gmail_message_id', '')} and Notion record {notion_id}. Sending is verified; commercial success is still an outcome to track, not something I am assuming.",
            {"execution_status": "proposal_commercial_state_sync_verified", "notion_receipt": notion_id, "notion_evidence": dict(evidence), "gmail_message_id": pending.get("gmail_message_id", ""), "external_action_taken": True},
        )

    @staticmethod
    def _first_text(evidence: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = evidence.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        return ""

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending_send": None, "pending_notion": None, "last_completed": None}
        return value if isinstance(value, dict) else {"pending_send": None, "pending_notion": None, "last_completed": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)
