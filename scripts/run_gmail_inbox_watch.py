from __future__ import annotations

import json
import os
import sys
from email.utils import parseaddr
from pathlib import Path
from urllib import request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.telegram_outbound import TelegramConfig, TelegramDeliveryError, TelegramSender  # noqa: E402
from runtime.tony_dispatch_adapters import build_http_dispatchers  # noqa: E402
from runtime.tony_gmail_inbox_watch import GmailInboxWatchService  # noqa: E402


def ingest_email_candidate(item: dict[str, object], webhook_url: str) -> bool:
    message_id = str(item.get("message_id") or "").strip()
    sender_name, sender_email = parseaddr(str(item.get("from") or ""))
    if not message_id or not sender_email:
        return False
    payload = {
        "lead_id": f"gmail:{message_id}",
        "inbound_message_id": message_id,
        "source": "Email",
        "name": sender_name or sender_email,
        "email": sender_email,
        "challenge": str(item.get("snippet") or "")[:1000],
        "raw_answers": {
            "email_subject": str(item.get("subject") or "")[:500],
            "gmail_thread_id": str(item.get("thread_id") or ""),
            "person_to_person": True,
        },
        "submitted_at": str(item.get("date") or ""),
    }
    call = request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(call, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    return isinstance(result, dict) and result.get("ok") is True


def main() -> int:
    gmail = build_http_dispatchers().get("Gmail")
    if gmail is None:
        print(json.dumps({"status": "gmail_dispatcher_unavailable"}))
        return 1
    try:
        telegram = TelegramSender(TelegramConfig.from_env(os.environ))
    except TelegramDeliveryError as exc:
        print(json.dumps({"status": "telegram_unavailable", "error": str(exc)}))
        return 1

    runtime_root = Path(os.getenv("NARRATIIVE_RUNTIME_ROOT", ".runtime")).resolve()
    workspace_id = (
        os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip()
        or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip()
        or "agency"
    )
    state_path = runtime_root / "workspaces" / workspace_id / "gmail-inbox-watch" / "state.json"
    service = GmailInboxWatchService(
        gmail,
        state_path,
        lambda text: telegram.send(telegram.config.default_chat_id, text),
        ingest_lead_candidate=lambda item: ingest_email_candidate(
            item,
            os.getenv("NARRATIIVE_INBOUND_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/diagnostic-lead"),
        ),
    )
    try:
        result = service.run()
    except Exception as exc:
        print(json.dumps({"status": "inbox_watch_failed", "error": str(exc)}))
        return 1
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status != "unverified_read" else 1


if __name__ == "__main__":
    raise SystemExit(main())
