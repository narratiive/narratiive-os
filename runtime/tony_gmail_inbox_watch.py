from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Callable, Mapping


GmailRead = Callable[[dict[str, Any]], dict[str, Any]]
MessageSender = Callable[[str], None]
LeadCandidateIngestor = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True, slots=True)
class InboxWatchResult:
    status: str
    checked: int
    alerted: int
    candidates: int = 0
    ingested: int = 0
    ingest_failed: int = 0
    message_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked": self.checked,
            "alerted": self.alerted,
            "candidates": self.candidates,
            "ingested": self.ingested,
            "ingest_failed": self.ingest_failed,
            "message_ids": list(self.message_ids),
        }


class GmailInboxWatchService:
    """Surface new person-to-person inbox correspondence to Tony without mutation.

    The watcher deliberately does not reply, label, archive, create CRM records or
    otherwise interpret email as an instruction. It only sends an internal Telegram
    attention note containing bounded Gmail evidence. Tony's normal approval and
    workflow controls govern every subsequent action.
    """

    def __init__(
        self,
        gmail: GmailRead,
        state_path: str | Path,
        send_message: MessageSender,
        *,
        ingest_lead_candidate: LeadCandidateIngestor | None = None,
        owned_addresses: tuple[str, ...] = ("hello@narratiive.com", "tony@narratiive.com"),
    ) -> None:
        self.gmail = gmail
        self.state_path = Path(state_path)
        self.send_message = send_message
        self.ingest_lead_candidate = ingest_lead_candidate
        self.owned_addresses = {value.casefold() for value in owned_addresses}

    def run(self) -> InboxWatchResult:
        evidence = self.gmail(
            {
                "worker": "Gmail",
                "surface": "gmail",
                "action": "List recent inbox correspondence for Tony attention triage without changing Gmail",
                "operation": "search",
                "instruction": "Return bounded inbox metadata only. Do not send, label, archive or mutate Gmail.",
                "target": {"query": "in:inbox newer_than:7d", "max_results": 10},
                "execution_mode": "autonomous_read",
                "eligible": True,
                "state": "ready_for_autonomous_dispatch",
                "execution_truth": "not_dispatched",
                "source": "gmail_inbox_watch",
            }
        )
        if not self._verified(evidence):
            return InboxWatchResult("unverified_read", 0, 0)

        items = [dict(item) for item in evidence.get("results", []) if isinstance(item, Mapping)]
        seen = self._load_seen()
        unseen = [item for item in items if self._message_id(item) not in seen]
        actionable = [item for item in unseen if self._is_person_to_person(item)]
        candidates = [item for item in actionable if self._is_lead_candidate(item)]

        ingested_ids: set[str] = set()
        ingest_failed = 0
        if self.ingest_lead_candidate is not None:
            for item in candidates:
                try:
                    if self.ingest_lead_candidate(item):
                        ingested_ids.add(self._message_id(item))
                    else:
                        ingest_failed += 1
                except Exception:
                    ingest_failed += 1

        if actionable:
            self.send_message(self._render(actionable))

        candidate_ids = {self._message_id(item) for item in candidates}
        current_ids = [
            self._message_id(item)
            for item in items
            if self._message_id(item)
            and (
                self._message_id(item) not in candidate_ids
                or self.ingest_lead_candidate is None
                or self._message_id(item) in ingested_ids
            )
        ]
        self._save_seen([*current_ids, *seen])
        return InboxWatchResult(
            "attention_sent" if actionable else "no_new_actionable_mail",
            len(items),
            len(actionable),
            len(candidates),
            len(ingested_ids),
            ingest_failed,
            tuple(self._message_id(item) for item in actionable),
        )

    @staticmethod
    def _is_lead_candidate(item: Mapping[str, Any]) -> bool:
        text = " ".join(
            (
                str(item.get("subject") or ""),
                str(item.get("snippet") or ""),
            )
        ).casefold()
        signals = (
            "introduction",
            "intro ",
            "enquiry",
            "inquiry",
            "new conversation",
            "recommended you",
            "suggested i contact",
            "looking for",
            "work together",
            "campaign",
            "proposal",
            "help with",
            "arrange a conversation",
            "book a call",
        )
        return any(signal in text for signal in signals)

    @staticmethod
    def _verified(evidence: Any) -> bool:
        return (
            isinstance(evidence, Mapping)
            and evidence.get("verified") is True
            and evidence.get("read_only") is True
            and evidence.get("mutation_count") == 0
            and isinstance(evidence.get("results"), list)
        )

    @staticmethod
    def _message_id(item: Mapping[str, Any]) -> str:
        return str(item.get("message_id") or "").strip()

    def _is_person_to_person(self, item: Mapping[str, Any]) -> bool:
        labels = {str(value).upper() for value in item.get("label_ids", [])}
        if "INBOX" not in labels or labels.intersection({"SPAM", "TRASH"}):
            return False
        sender = parseaddr(str(item.get("from") or ""))[1].casefold()
        if not sender or sender in self.owned_addresses:
            return False
        auto_submitted = str(item.get("auto_submitted") or "").strip().casefold()
        precedence = str(item.get("precedence") or "").strip().casefold()
        if auto_submitted and auto_submitted != "no":
            return False
        if precedence in {"bulk", "junk", "list"} or item.get("list_unsubscribe") is True:
            return False
        return True

    @staticmethod
    def _render(items: list[dict[str, Any]]) -> str:
        lines = [
            "Tony inbox attention — new person-to-person correspondence:",
        ]
        for item in items[:5]:
            sender = " ".join(str(item.get("from") or "Unknown sender").split())[:180]
            subject = " ".join(str(item.get("subject") or "(no subject)").split())[:180]
            snippet = " ".join(str(item.get("snippet") or "").split())[:320]
            message_id = str(item.get("message_id") or "")
            lines.append(f"- {sender} — {subject}\n  {snippet}\n  Gmail message: {message_id}")
        if len(items) > 5:
            lines.append(f"...and {len(items) - 5} more.")
        lines.append(
            "I have not replied, labelled, archived or changed any message. Read the exact message, check the Notion record, and prepare the appropriate next action; any reply or persisted change still requires its normal human approval."
        )
        return "\n".join(lines)[:3900]

    def _load_seen(self) -> list[str]:
        if not self.state_path.is_file():
            return []
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        values = payload.get("seen_message_ids", []) if isinstance(payload, dict) else []
        return [str(value) for value in values if str(value).strip()][:500]

    def _save_seen(self, message_ids: list[str]) -> None:
        deduplicated = list(dict.fromkeys(value for value in message_ids if value))[:500]
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.", suffix=".tmp", dir=self.state_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "last_successful_check_at": datetime.now(timezone.utc).isoformat(),
                        "seen_message_ids": deduplicated,
                    },
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
