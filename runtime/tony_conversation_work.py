from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


class ConversationWorkError(RuntimeError):
    """Raised when durable conversational work cannot be safely advanced."""


class ConversationExecutor(Protocol):
    def __call__(self, text: str, work_id: str) -> str: ...


class ConversationSender(Protocol):
    def __call__(self, chat_id: str, text: str) -> Mapping[str, Any] | None: ...


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ConversationAcceptance:
    work_id: str
    acknowledgement: str
    replay: bool


class SubstantiveConversationRouter:
    """Separate ordinary chat from requests that commission material work.

    Routing is based on the requested kind of work, not prompt size. Length is
    intentionally absent so a long conversational message can remain synchronous
    and a short instruction such as "research this" is still durable.
    """

    _WORK_MARKERS = (
        "research",
        "investigate",
        "commission",
        "full client acceptance",
        "acceptance test",
        "growth blueprint",
        "choose a company",
        "choose/propose",
        "propose a suitable",
        "prepare a strategy",
        "produce a report",
        "specialist",
        "research analyst",
        "strategy director",
        "creative director",
    )

    def requires_durable_work(self, text: str) -> bool:
        normalised = " ".join(str(text).casefold().split())
        return any(marker in normalised for marker in self._WORK_MARKERS)

    @staticmethod
    def acknowledgement(text: str) -> str:
        normalised = str(text).casefold()
        if "research" in normalised or "company" in normalised or "investigat" in normalised:
            return "I’ll investigate this properly and come back here with a considered answer."
        return "I’m commissioning this now and I’ll come back here when the work is ready."


class FileConversationWorkStore:
    """Durable work snapshots plus an append-only event history.

    A single advisory lock covers submission, leasing and transitions across the
    bridge and worker processes. Snapshots are derived operational state; every
    transition is also fsynced to JSONL so recovery does not rewrite history.
    """

    def __init__(self, root: Path, *, clock: Clock | None = None) -> None:
        self.root = root
        self.jobs = root / "jobs"
        self.events_path = root / "events.jsonl"
        self.lock_path = root / ".lock"
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.jobs.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def work_id(*, workspace_id: str, chat_id: str, message_id: str, update_id: str, text: str) -> str:
        stable_message = message_id.strip() or update_id.strip()
        if not stable_message:
            stable_message = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:20]
        identity = f"telegram\0{workspace_id.strip()}\0{chat_id.strip()}\0{stable_message}"
        return "telegram-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]

    def submit(
        self,
        *,
        workspace_id: str,
        chat_id: str,
        message_id: str,
        update_id: str,
        text: str,
        acknowledgement: str,
    ) -> tuple[dict[str, Any], bool]:
        for label, value in (("workspace_id", workspace_id), ("chat_id", chat_id), ("text", text)):
            if not str(value).strip():
                raise ConversationWorkError(f"{label} is required")
        work_id = self.work_id(
            workspace_id=workspace_id,
            chat_id=chat_id,
            message_id=message_id,
            update_id=update_id,
            text=text,
        )
        with self._locked():
            existing = self._read_unlocked(work_id)
            if existing is not None:
                return existing, True
            now = self._now()
            record: dict[str, Any] = {
                "schema_version": 1,
                "work_id": work_id,
                "correlation": {
                    "channel": "telegram",
                    "workspace_id": workspace_id.strip(),
                    "chat_id": chat_id.strip(),
                    "message_id": message_id.strip(),
                    "update_id": update_id.strip(),
                },
                "request": text.strip(),
                "acknowledgement": acknowledgement.strip(),
                "state": "queued",
                "attempt_count": 0,
                "delivery_attempt_count": 0,
                "lease_owner": "",
                "lease_expires_at": "",
                "result": "",
                "failure": "",
                "delivery_evidence": {},
                "external_action_taken": False,
                "created_at": now,
                "updated_at": now,
            }
            self._transition_unlocked(record, "conversation_work.queued")
            return record, False

    def get(self, work_id: str) -> dict[str, Any] | None:
        with self._locked():
            return self._read_unlocked(work_id)

    def claim_next(self, worker_id: str, *, lease_seconds: int) -> dict[str, Any] | None:
        if not worker_id.strip() or lease_seconds <= 0:
            raise ConversationWorkError("worker_id and a positive lease are required")
        with self._locked():
            now = self.clock().astimezone(timezone.utc)
            for path in sorted(self.jobs.glob("*.json"), key=lambda item: item.stat().st_mtime):
                record = self._read_path(path)
                state = str(record.get("state") or "")
                if state in {"running", "delivering"} and self._lease_active(record, now):
                    continue
                if state in {"running", "delivering"}:
                    record["state"] = "queued" if state == "running" else "ready_to_deliver"
                    record["lease_owner"] = ""
                    record["lease_expires_at"] = ""
                    self._transition_unlocked(record, "conversation_work.recovered")
                    state = "queued"
                if state not in {"queued", "ready_to_deliver"}:
                    continue
                record["state"] = "delivering" if state == "ready_to_deliver" else "running"
                record["lease_owner"] = worker_id.strip()
                record["lease_expires_at"] = (now + timedelta(seconds=lease_seconds)).isoformat()
                if state == "queued":
                    record["attempt_count"] = int(record.get("attempt_count") or 0) + 1
                    event = "conversation_work.started"
                else:
                    record["delivery_attempt_count"] = int(record.get("delivery_attempt_count") or 0) + 1
                    event = "conversation_work.delivery_started"
                self._transition_unlocked(record, event)
                return record
        return None

    def result_ready(self, work_id: str, worker_id: str, result: str) -> dict[str, Any]:
        with self._locked():
            record = self._owned_unlocked(work_id, worker_id, "running")
            if not result.strip():
                raise ConversationWorkError("result is required")
            record.update(state="delivering", result=result.strip(), failure="")
            record["delivery_attempt_count"] = int(record.get("delivery_attempt_count") or 0) + 1
            self._transition_unlocked(record, "conversation_work.result_ready")
            return record

    def delivered(
        self,
        work_id: str,
        worker_id: str,
        delivery_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._locked():
            record = self._owned_unlocked(work_id, worker_id, "delivering")
            record.update(
                state="completed",
                lease_owner="",
                lease_expires_at="",
                external_action_taken=True,
                delivery_evidence=dict(delivery_evidence or {}),
            )
            self._transition_unlocked(record, "conversation_work.delivered")
            return record

    def failure_notified(self, work_id: str, delivery_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._locked():
            record = self._read_unlocked(work_id)
            if record is None or record.get("state") != "failed":
                raise ConversationWorkError(f"work {work_id} is not failed")
            record["external_action_taken"] = True
            record["delivery_evidence"] = dict(delivery_evidence or {})
            self._transition_unlocked(record, "conversation_work.failure_notified")
            return record

    def retry_or_fail(self, work_id: str, worker_id: str, error: str, *, max_attempts: int) -> dict[str, Any]:
        with self._locked():
            record = self._read_unlocked(work_id)
            if record is None or record.get("lease_owner") != worker_id:
                raise ConversationWorkError(f"work {work_id} is not leased by {worker_id}")
            generation_failure = record.get("state") == "running"
            attempts = int(record.get("attempt_count" if generation_failure else "delivery_attempt_count") or 0)
            record["state"] = "queued" if generation_failure and attempts < max_attempts else (
                "ready_to_deliver" if not generation_failure and attempts < max_attempts else "failed"
            )
            record["failure"] = str(error).strip()[:500] or "worker failure"
            record["lease_owner"] = ""
            record["lease_expires_at"] = ""
            self._transition_unlocked(
                record,
                "conversation_work.retry_scheduled" if record["state"] != "failed" else "conversation_work.failed",
            )
            return record

    def _owned_unlocked(self, work_id: str, worker_id: str, state: str) -> dict[str, Any]:
        record = self._read_unlocked(work_id)
        if record is None or record.get("state") != state or record.get("lease_owner") != worker_id:
            raise ConversationWorkError(f"work {work_id} is not {state} for {worker_id}")
        return record

    def _transition_unlocked(self, record: dict[str, Any], event_type: str) -> None:
        record["updated_at"] = self._now()
        event = {
            "event_type": event_type,
            "recorded_at": record["updated_at"],
            "work_id": record["work_id"],
            "workspace_id": record["correlation"]["workspace_id"],
            "chat_id": record["correlation"]["chat_id"],
            "message_id": record["correlation"]["message_id"],
            "update_id": record["correlation"]["update_id"],
            "state": record["state"],
            "attempt_count": record["attempt_count"],
            "delivery_attempt_count": record["delivery_attempt_count"],
            "failure": record.get("failure") or "",
            "external_action_taken": bool(record.get("external_action_taken")),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._write_unlocked(record)

    def _write_unlocked(self, record: Mapping[str, Any]) -> None:
        target = self.jobs / f"{record['work_id']}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(dict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, target)

    def _read_unlocked(self, work_id: str) -> dict[str, Any] | None:
        path = self.jobs / f"{work_id}.json"
        return self._read_path(path) if path.exists() else None

    @staticmethod
    def _read_path(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConversationWorkError(f"conversation work state is unreadable: {exc}") from exc
        if not isinstance(value, dict):
            raise ConversationWorkError("conversation work state must be an object")
        return value

    @staticmethod
    def _lease_active(record: Mapping[str, Any], now: datetime) -> bool:
        raw = str(record.get("lease_expires_at") or "")
        return bool(raw and datetime.fromisoformat(raw) > now)

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()

    def _locked(self):
        store = self

        class Lock:
            def __enter__(self):
                store.lock_path.parent.mkdir(parents=True, exist_ok=True)
                self.handle = store.lock_path.open("a+", encoding="utf-8")
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
                return self

            def __exit__(self, *_):
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                self.handle.close()

        return Lock()


class TonyConversationIngress:
    def __init__(self, store: FileConversationWorkStore, *, workspace_id: str, router: SubstantiveConversationRouter | None = None) -> None:
        self.store = store
        self.workspace_id = workspace_id.strip()
        self.router = router or SubstantiveConversationRouter()

    def requires_durable_work(self, text: str) -> bool:
        return self.router.requires_durable_work(text)

    def accept(self, request: Mapping[str, Any], text: str) -> ConversationAcceptance:
        acknowledgement = self.router.acknowledgement(text)
        record, replay = self.store.submit(
            workspace_id=self.workspace_id,
            chat_id=str(request.get("chat_id") or ""),
            message_id=str(request.get("message_id") or ""),
            update_id=str(request.get("update_id") or ""),
            text=text,
            acknowledgement=acknowledgement,
        )
        return ConversationAcceptance(record["work_id"], str(record["acknowledgement"]), replay)


class TonyConversationWorker:
    FAILURE_FOLLOWUP = "I’m sorry — I couldn’t complete that work reliably. I’ve kept the work record and failure evidence so it can be retried or inspected."

    def __init__(self, store: FileConversationWorkStore, executor: ConversationExecutor, sender: ConversationSender, *, worker_id: str | None = None, lease_seconds: int = 1800, max_attempts: int = 3) -> None:
        self.store = store
        self.executor = executor
        self.sender = sender
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts

    def run_once(self) -> dict[str, Any] | None:
        work = self.store.claim_next(self.worker_id, lease_seconds=self.lease_seconds)
        if work is None:
            return None
        work_id = str(work["work_id"])
        try:
            if work["state"] == "running":
                result = self.executor(str(work["request"]), work_id)
                work = self.store.result_ready(work_id, self.worker_id, result)
            if work["state"] == "delivering":
                evidence = self.sender(str(work["correlation"]["chat_id"]), str(work["result"]))
                return self.store.delivered(work_id, self.worker_id, evidence)
        except Exception as exc:
            failed = self.store.retry_or_fail(work_id, self.worker_id, f"{type(exc).__name__}: {exc}", max_attempts=self.max_attempts)
            if failed["state"] == "failed":
                try:
                    evidence = self.sender(str(failed["correlation"]["chat_id"]), self.FAILURE_FOLLOWUP)
                    self.store.failure_notified(work_id, evidence)
                except Exception:
                    pass
            return failed
        return work
