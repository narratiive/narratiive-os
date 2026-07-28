from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.telegram_outbound import TelegramConfig, TelegramDeliveryError, TelegramSender  # noqa: E402
from runtime.interruption_policy import FixedCooldownInterruptionPolicy  # noqa: E402
from runtime.policy_governed_escalation import PolicyGovernedMaterialEscalationService  # noqa: E402
from runtime.proactive_executive_delivery import (  # noqa: E402
    FileDeliveryKeyStore,
    FileLastEscalationStore,
    LatestDeliveryStatusStore,
    ProactiveDeliveryLockContended,
    ProactiveDeliveryLockError,
    WorkspaceDeliveryLock,
)
from scripts.run_proactive_brief import (  # noqa: E402
    ALREADY_RUNNING_STATUS,
    FAILING_STATUSES,
    ProactiveBriefConfigurationError,
    _combined,
    _event_recorder,
    _lock_path,
    _status_recorder,
    _workspace_id_from_env,
    build_components,
)


def run(*, simulate_transport_failure: bool = False) -> dict[str, Any]:
    runtime_root = Path(os.getenv("NARRATIIVE_RUNTIME_ROOT", ".runtime")).resolve()
    workspace_id = _workspace_id_from_env()

    try:
        workspace_runtime, _, mission_control_loader = build_components(
            runtime_root=runtime_root, workspace_id=workspace_id
        )
    except ProactiveBriefConfigurationError as exc:
        return {"status": "configuration_blocked", "error": str(exc)}

    status_store = LatestDeliveryStatusStore(
        workspace_runtime.paths.root / "proactive-delivery" / "latest-status.json"
    )
    recorder = _combined(
        _event_recorder(workspace_runtime), _status_recorder(status_store, "escalation")
    )

    try:
        telegram = TelegramSender(TelegramConfig.from_env(os.environ))
    except TelegramDeliveryError as exc:
        recorder(
            {
                "event_type": "executive_escalation.delivery_blocked",
                "command": "escalation",
                "status": "configuration_blocked",
                "error": str(exc),
            }
        )
        return {"status": "configuration_blocked", "error": str(exc)}

    def send(chat_id: str, text: str) -> None:
        if simulate_transport_failure:
            raise TelegramDeliveryError("simulated transport failure")
        telegram.send(chat_id, text)

    min_interval_seconds = int(
        os.getenv("TONY_PROACTIVE_ESCALATION_MIN_INTERVAL_SECONDS", "1800")
    )
    service = PolicyGovernedMaterialEscalationService(
        mission_control_loader=mission_control_loader,
        send_message=send,
        key_store=FileDeliveryKeyStore(
            workspace_runtime.paths.root / "proactive-delivery" / "escalation-keys.json"
        ),
        last_sent_store=FileLastEscalationStore(
            workspace_runtime.paths.root / "proactive-delivery" / "escalation-last-sent.json"
        ),
        interruption_policy=FixedCooldownInterruptionPolicy(
            min_interval_seconds=min_interval_seconds
        ),
        record_event=recorder,
        max_attempts=int(os.getenv("TONY_PROACTIVE_MAX_ATTEMPTS", "3")),
    )

    try:
        with WorkspaceDeliveryLock(_lock_path(workspace_runtime)):
            result = service.escalate(
                workspace_id=workspace_id,
                chat_id=telegram.config.default_chat_id,
            )
        return result.to_dict()
    except ProactiveDeliveryLockContended as exc:
        return {"status": ALREADY_RUNNING_STATUS, "error": str(exc)}
    except ProactiveDeliveryLockError as exc:
        recorder(
            {
                "event_type": "executive_escalation.delivery_blocked",
                "command": "escalation",
                "status": "lock_unavailable",
                "error": str(exc),
            }
        )
        return {"status": "lock_unavailable", "error": str(exc)}


def main() -> int:
    result = run()
    ok = result.get("status") not in FAILING_STATUSES
    print(json.dumps({"ok": ok, "escalation": result}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
