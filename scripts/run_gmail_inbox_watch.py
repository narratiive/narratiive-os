from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.telegram_outbound import TelegramConfig, TelegramDeliveryError, TelegramSender  # noqa: E402
from runtime.tony_dispatch_adapters import build_http_dispatchers  # noqa: E402
from runtime.tony_gmail_inbox_watch import GmailInboxWatchService  # noqa: E402


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
