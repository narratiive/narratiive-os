from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.telegram_outbound import TelegramConfig, TelegramSender  # noqa: E402
from openclaw.tony_live_bridge import build_app  # noqa: E402
from runtime.discovery_monitor import TonyDiscoveryMonitor  # noqa: E402
from runtime.proactive_executive_delivery import (  # noqa: E402
    ProactiveDeliveryLockContended,
    WorkspaceDeliveryLock,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile Discovery bookings and process completed Gemini evidence through Tony's governed services."
    )
    parser.add_argument("--recover-gemini-file-id")
    parser.add_argument("--lead-id")
    parser.add_argument("--company")
    parser.add_argument("--meeting-ended-at")
    parser.add_argument("--confirmed-by")
    parser.add_argument("--rationale")
    return parser


def run_monitor_once(*, app=None, notify=None) -> dict[str, object]:
    try:
        app = app or build_app(recover_workflows=False)
    except (Exception, SystemExit) as exc:
        return {
            "ok": False,
            "status": "discovery_monitor_configuration_blocked",
            "error": str(exc),
        }
    discovery_service = app.discovery_outcome_service
    post_discovery_service = app.post_discovery_service
    leads_loader = app.authoritative_lead_loader
    if discovery_service is None or post_discovery_service is None or leads_loader is None:
        return {"ok": False, "status": "discovery_monitor_unavailable"}
    root = Path(os.getenv("TONY_DISCOVERY_MONITOR_ROOT", str(REPOSITORY_ROOT / ".runtime" / "discovery-monitor"))).resolve()
    if notify is None:
        telegram = TelegramSender(TelegramConfig.from_env(os.environ))

        def notify(text: str) -> None:
            telegram.send(telegram.config.default_chat_id, text)

    monitor = TonyDiscoveryMonitor(
        discovery_service=discovery_service,
        post_discovery_service=post_discovery_service,
        leads_loader=leads_loader,
        notify=notify,
        state_path=root / "state.json",
        events_path=root / "events.jsonl",
    )
    try:
        with WorkspaceDeliveryLock(root / "monitor.lock"):
            return {"ok": True, **monitor.run()}
    except ProactiveDeliveryLockContended:
        return {
            "ok": True,
            "status": "already_running",
            "external_action_taken": False,
            "notification_sent": False,
        }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_app(recover_workflows=False)
    discovery_service = app.discovery_outcome_service
    if discovery_service is None or app.post_discovery_service is None or app.authoritative_lead_loader is None:
        print(json.dumps({"ok": False, "status": "discovery_monitor_unavailable"}, sort_keys=True))
        return 1

    if args.recover_gemini_file_id:
        recovery = discovery_service.adopt_verified_gemini_document(
            file_id=args.recover_gemini_file_id,
            lead_id=args.lead_id or "",
            company=args.company or "",
            meeting_ended_at=args.meeting_ended_at or "",
            confirmed_by=args.confirmed_by or "",
            rationale=args.rationale or "",
        )
        if recovery.data.get("execution_status") != "discovery_outcome_tracking_active":
            print(json.dumps({"ok": False, **recovery.to_dict()}, indent=2, sort_keys=True))
            return 1

    result = run_monitor_once(app=app)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
