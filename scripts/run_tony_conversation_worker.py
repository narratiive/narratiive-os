from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.telegram_outbound import TelegramConfig, TelegramSender  # noqa: E402
from openclaw.tony_agent_gateway import build_gateway  # noqa: E402
from runtime.tony_conversation_work import (  # noqa: E402
    FileConversationWorkStore,
    TonyConversationWorker,
)


def build_worker() -> TonyConversationWorker:
    root = Path(
        os.getenv(
            "TONY_CONVERSATION_WORK_ROOT",
            str(REPOSITORY_ROOT / ".runtime" / "conversation-work"),
        )
    ).resolve()
    gateway = build_gateway()
    telegram = TelegramSender(TelegramConfig.from_env(os.environ))
    return TonyConversationWorker(
        FileConversationWorkStore(root),
        gateway.converse_for_work,
        telegram.send,
        lease_seconds=int(os.getenv("TONY_CONVERSATION_LEASE_SECONDS", "2100")),
        max_attempts=int(os.getenv("TONY_CONVERSATION_MAX_ATTEMPTS", "3")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tony's durable conversational work queue")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    worker = build_worker()
    if args.once:
        worker.run_once()
        return

    stopping = False

    def stop(*_args) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        if worker.run_once() is None:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    main()
