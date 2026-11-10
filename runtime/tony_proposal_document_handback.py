"""Governed manual handback for a Claude-produced proposal document.

Matt takes the proposal commission brief to Claude himself (outside this
runtime) and returns the finished document. This module binds the exact
returned document to its version, producer, checksum and source brief, and
keeps three separate approval gates apart:

1. registering the document (never implies approval);
2. approving the exact registered document version;
3. approving the exact email (recipient, subject, body, attachment) built
   from it — a changed body, recipient or attachment invalidates that
   approval even if the underlying document is still approved.

No send capability exists here. Real client sending stays disabled until a
separately governed, independently reviewed client-sending adapter exists;
this only ever prepares an unsent Gmail draft to the authorised internal
review address or a visibly synthetic test address.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.tony_command_service import CommandResponse

INTERNAL_REVIEW_RECIPIENT = "hello@narratiive.com"
MAX_BYTES = 10_000_000


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _is_synthetic_test_recipient(recipient: str) -> bool:
    lowered = recipient.casefold()
    return any(marker in lowered for marker in ("safe-test", "safe_test", "test.invalid", "example.invalid", ".invalid"))


class TonyProposalHandbackCommandService:
    def __init__(self, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path, documents_root: Path) -> None:
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.documents_root = documents_root
        self.state = self._load()

    # ---- registration (never implies approval) -------------------------------------------------

    def register(
        self,
        *,
        brief_id: str,
        lead_id: str,
        company: str,
        contact: str,
        producer: str,
        version: str,
        title: str,
        filename: str,
        content_base64: str,
        registered_by: str,
    ) -> CommandResponse:
        required = {"brief_id": brief_id, "lead_id": lead_id, "producer": producer, "version": version, "title": title, "filename": filename, "content_base64": content_base64, "registered_by": registered_by}
        missing = [key for key, value in required.items() if not _text(value)]
        if missing:
            return self._error("proposal_handback_requires_exact_fields", f"Registering the proposal document requires: {', '.join(missing)}.")
        if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
            return self._error("proposal_handback_requires_pdf", "Only an actual PDF document is accepted for proposal handback.")
        try:
            data = base64.b64decode(content_base64, validate=True)
        except Exception:
            return self._error("proposal_handback_content_invalid", "The supplied document content is not valid base64.")
        if not data or len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
            return self._error("proposal_handback_not_a_pdf", "The supplied bytes are not a real, bounded-size PDF document.")
        checksum = hashlib.sha256(data).hexdigest()
        recovery_id = f"proposal-handback-{checksum[:24]}"
        documents = dict(self.state.get("documents") or {})
        existing = documents.get(recovery_id)
        if existing is not None:
            return CommandResponse(
                "proposal_handback",
                "healthy",
                f"This exact document is already registered as {recovery_id}. Registration is not approval; nothing has changed.",
                {"execution_status": "proposal_document_already_registered", "proposal_handback": dict(existing), "external_action_taken": False},
            )
        directory = self.documents_root / checksum
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / filename
        if target.is_symlink():
            return self._error("proposal_handback_rejects_symlinks", "Document symlinks are not accepted.")
        if not target.exists():
            with target.open("xb") as handle:
                handle.write(data)
        record = {
            "recovery_id": recovery_id,
            "brief_id": _text(brief_id),
            "lead_id": _text(lead_id),
            "company": _text(company),
            "contact": _text(contact),
            "producer": _text(producer),
            "version": _text(version),
            "title": _text(title),
            "filename": filename,
            "checksum": checksum,
            "path": str(target),
            "registered_by": _text(registered_by),
            "registered_at": self._now(),
            "approval_status": "not_accepted_on_registration",
        }
        documents[recovery_id] = record
        self.state["documents"] = documents
        self._persist()
        return CommandResponse(
            "proposal_handback",
            "healthy",
            f"Registered the returned proposal document as {recovery_id} (version {version}, from {producer}). Registration does not approve it; Matt must separately approve this exact version before I can prepare any email draft from it.",
            {"execution_status": "proposal_document_registered", "proposal_handback": dict(record), "external_action_taken": False},
        )

    # ---- document approval (separate from registration and from email approval) ---------------

    def approve_document(self, recovery_id: str, *, approver: str, rationale: str) -> CommandResponse:
        record = (self.state.get("documents") or {}).get(recovery_id)
        if not isinstance(record, dict):
            return self._error("proposal_document_not_found", f"No registered proposal document matches {recovery_id}.")
        if not _text(approver) or not _text(rationale):
            return self._error("proposal_document_approval_requires_exact_fields", "Approving the proposal document requires an authenticated approver and a rationale.")
        approvals = list(self.state.get("document_approvals") or [])
        if any(item.get("recovery_id") == recovery_id and item.get("checksum") == record["checksum"] for item in approvals):
            return CommandResponse("proposal_handback", "healthy", f"{recovery_id} is already approved at its exact registered checksum; this did not create a duplicate approval.", {"execution_status": "proposal_document_already_approved", "proposal_handback": dict(record), "external_action_taken": False})
        approvals.append({"recovery_id": recovery_id, "checksum": record["checksum"], "approver": _text(approver), "rationale": _text(rationale), "approved_at": self._now()})
        self.state["document_approvals"] = approvals
        self._persist()
        return CommandResponse(
            "proposal_handback",
            "healthy",
            f"{approver} approved proposal document {recovery_id} (version {record['version']}) at its exact registered checksum. This approves the document only; the email and its attachment still require a separate approval before anything is sent.",
            {"execution_status": "proposal_document_approved", "proposal_handback": dict(record), "external_action_taken": False},
        )

    def _document_approval(self, recovery_id: str, checksum: str) -> dict[str, Any] | None:
        for item in self.state.get("document_approvals") or []:
            if item.get("recovery_id") == recovery_id and item.get("checksum") == checksum:
                return item
        return None

    # ---- unsent email draft, bound to the exact approved document -------------------------------

    def prepare_email_draft(self, recovery_id: str, *, recipient: str, subject: str, body: str) -> CommandResponse:
        record = (self.state.get("documents") or {}).get(recovery_id)
        if not isinstance(record, dict):
            return self._error("proposal_document_not_found", f"No registered proposal document matches {recovery_id}.")
        if self._document_approval(recovery_id, record["checksum"]) is None:
            return self._error("proposal_document_approval_required", f"Proposal document {recovery_id} is not yet approved at its exact registered checksum; I will not prepare an email draft from an unapproved document.")
        if not all(_text(value) for value in (recipient, subject, body)):
            return self._error("proposal_email_requires_exact_fields", "Preparing the email draft requires an exact recipient, subject and body.")
        if recipient.casefold() != INTERNAL_REVIEW_RECIPIENT and not _is_synthetic_test_recipient(recipient):
            return self._error("proposal_email_recipient_not_authorised", f"Real client sending is not enabled in this task; the recipient must be the authorised internal review address ({INTERNAL_REVIEW_RECIPIENT}) or a visibly synthetic test address.")
        gmail = self.dispatchers.get("Gmail")
        if gmail is None:
            return self._error("proposal_email_dispatcher_unavailable", "No live Gmail dispatcher is configured, so I cannot prepare the draft.")
        path = Path(record["path"])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["checksum"]:
            return self._error("proposal_document_changed", "The registered document's bytes no longer match its approved checksum; I will not draft from a changed file.")
        action_digest = self._action_digest(record["checksum"], recipient, subject, body)
        contract = {
            "execution_mode": "approved_write",
            "approval_granted": True,
            "operation": "create_draft",
            "idempotency_key": f"proposal-draft:{action_digest}",
            "payload": {
                "recipient_email": recipient,
                "subject": subject,
                "body": body,
                "attachments": [{"filename": record["filename"], "mime_type": "application/pdf", "content_base64": base64.b64encode(data).decode()}],
            },
        }
        try:
            receipt = gmail(contract)
        except Exception as exc:
            return self._error("proposal_email_draft_failed", f"Preparing the unsent draft failed: {exc}")
        if receipt.get("verified") is not True or receipt.get("sent") is not False or not receipt.get("draft_id"):
            return self._error("proposal_email_draft_unverified", "Gmail did not return a verified unsent draft; nothing has been queued to send.")
        drafts = dict(self.state.get("drafts") or {})
        draft = {
            "recovery_id": recovery_id,
            "draft_id": str(receipt.get("draft_id")),
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "attachment_checksum": record["checksum"],
            "action_digest": action_digest,
            "prepared_at": self._now(),
            "send_authorised": False,
        }
        drafts[recovery_id] = draft
        self.state["drafts"] = drafts
        self._persist()
        return CommandResponse(
            "proposal_handback",
            "healthy",
            f"Prepared an unsent Gmail draft for {recipient} with subject '{subject}' and the exact approved proposal attached. Nothing has been sent. Matt must separately approve this exact email and attachment before any send becomes possible, and real client sending remains disabled in this task regardless.",
            {"execution_status": "proposal_email_draft_ready", "proposal_email_draft": dict(draft), "external_action_taken": False},
        )

    def approve_email(self, recovery_id: str, *, approver: str, rationale: str) -> CommandResponse:
        draft = (self.state.get("drafts") or {}).get(recovery_id)
        if not isinstance(draft, dict):
            return self._error("proposal_email_draft_not_found", f"No prepared email draft matches {recovery_id}.")
        if not _text(approver) or not _text(rationale):
            return self._error("proposal_email_approval_requires_exact_fields", "Approving the email requires an authenticated approver and a rationale.")
        approvals = list(self.state.get("email_approvals") or [])
        approvals.append({"recovery_id": recovery_id, "action_digest": draft["action_digest"], "approver": _text(approver), "rationale": _text(rationale), "approved_at": self._now()})
        self.state["email_approvals"] = approvals
        self._persist()
        return CommandResponse(
            "proposal_handback",
            "healthy",
            f"{approver} approved this exact email (recipient, subject, body and attachment) for {recovery_id}. Real client sending remains disabled; this approval only establishes that the exact email is authorised if and when a governed send capability exists.",
            {"execution_status": "proposal_email_approved", "proposal_email_draft": dict(draft), "external_action_taken": False, "send_enabled": False},
        )

    def email_approval_status(self, recovery_id: str) -> str:
        """'approved' only if the live draft's content still matches the digest that was approved; a changed body, recipient or attachment invalidates it."""
        draft = (self.state.get("drafts") or {}).get(recovery_id)
        if not isinstance(draft, dict):
            return "no_draft"
        latest = None
        for item in self.state.get("email_approvals") or []:
            if item.get("recovery_id") == recovery_id:
                latest = item
        if latest is None:
            return "awaiting_approval"
        return "approved" if latest.get("action_digest") == draft.get("action_digest") else "invalidated_by_change"

    @staticmethod
    def _action_digest(checksum: str, recipient: str, subject: str, body: str) -> str:
        return hashlib.sha256("\0".join((checksum, recipient, subject, body)).encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _error(status: str, message: str) -> CommandResponse:
        return CommandResponse("proposal_handback", "healthy", message + " Nothing has been registered, approved or sent.", {"execution_status": status, "external_action_taken": False})

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"documents": {}, "document_approvals": [], "drafts": {}, "email_approvals": []}
        return value if isinstance(value, dict) else {"documents": {}, "document_approvals": [], "drafts": {}, "email_approvals": []}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)
