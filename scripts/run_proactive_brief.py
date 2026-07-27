from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from openclaw.tony_http_bridge import (  # noqa: E402
    build_brief_archive,
    build_engineering_handoff_loader,
    build_engineering_run_loader,
    build_github_work_loader,
    build_mission_control_loader,
    build_proactive_delivery_status_loader,
    load_growth_objects,
)
from openclaw.telegram_outbound import (  # noqa: E402
    TelegramConfig,
    TelegramDeliveryError,
    TelegramSender,
)
from runtime.composition import RuntimeComponents  # noqa: E402
from runtime.mission_control import MissionControlSnapshot  # noqa: E402
from runtime.proactive_executive_delivery import (  # noqa: E402
    DeliveryStatusRecord,
    FileDeliveryKeyStore,
    FileLastEscalationStore,
    LatestDeliveryStatusStore,
    MaterialEscalationService,
    ProactiveExecutiveDeliveryService,
)
from runtime.progress_engine import RepositoryProgressEngine  # noqa: E402
from runtime.repositories import WorkflowEvent  # noqa: E402
from runtime.repository_validator import GrowthObjectValidator  # noqa: E402
from runtime.tony_command_service import TonyCommandService  # noqa: E402
from runtime.tony_executive_commands import TonyExecutiveCommandService  # noqa: E402
from runtime.workspaces import WorkspaceNotFound, WorkspaceRuntimeManager  # noqa: E402


FAILING_STATUSES = {"generation_failed", "delivery_failed", "configuration_blocked"}
RUN_ID = "tony-proactive-delivery"


class ProactiveBriefConfigurationError(RuntimeError):
    """Raised when required scheduler configuration is missing or invalid."""


def _workspace_id_from_env() -> str:
    return (
        os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip()
        or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip()
    )


def build_components(
    *, runtime_root: Path, workspace_id: str
) -> tuple[RuntimeComponents, TonyExecutiveCommandService, Callable[[], MissionControlSnapshot]]:
    if not workspace_id:
        raise ProactiveBriefConfigurationError(
            "TONY_EXECUTIVE_WORKSPACE_ID (or TONY_GITHUB_WORKSPACE_ID) is required"
        )
    try:
        workspace_runtime = WorkspaceRuntimeManager(runtime_root, REPOSITORY_ROOT).runtime(
            workspace_id
        )
    except (ValueError, WorkspaceNotFound) as exc:
        raise ProactiveBriefConfigurationError(
            f"proactive delivery workspace is not configured: {exc}"
        ) from exc

    schema_path = Path(
        os.getenv(
            "TONY_GROWTH_OBJECT_SCHEMA",
            str(REPOSITORY_ROOT / "schemas" / "shared" / "growth-object.schema.json"),
        )
    )
    objects_root = Path(os.getenv("TONY_OBJECTS_ROOT", str(REPOSITORY_ROOT / "clients")))
    gateway_health_endpoint = os.getenv(
        "NARRATIIVE_GATEWAY_HEALTH_ENDPOINT", "http://127.0.0.1:8787/health"
    )
    validator = GrowthObjectValidator.from_path(schema_path)
    progress_engine = RepositoryProgressEngine(validator)
    object_loader = lambda: load_growth_objects(objects_root)  # noqa: E731

    brief_archive = build_brief_archive(runtime_root=runtime_root, repository_root=REPOSITORY_ROOT)
    if brief_archive.workspace_id != workspace_id:
        raise ProactiveBriefConfigurationError(
            "the executive brief workspace does not match the configured proactive workspace"
        )
    github_work_loader = build_github_work_loader(
        runtime_root=runtime_root,
        repository_root=REPOSITORY_ROOT,
        brief_archive=brief_archive,
    )
    engineering_handoff_loader = build_engineering_handoff_loader(
        runtime_root=runtime_root, repository_root=REPOSITORY_ROOT
    )
    engineering_run_loader = build_engineering_run_loader(
        runtime_root=runtime_root, repository_root=REPOSITORY_ROOT
    )
    proactive_status_loader = build_proactive_delivery_status_loader(
        runtime_root=runtime_root, repository_root=REPOSITORY_ROOT
    )
    mission_control_loader = build_mission_control_loader(
        progress_engine,
        object_loader,
        gateway_health_endpoint,
        github_work_loader,
        engineering_handoff_loader,
        engineering_run_loader,
        proactive_status_loader,
    )
    command_service = TonyCommandService(
        progress_engine,
        mission_control_loader=mission_control_loader,
        github_configured=github_work_loader is not None,
    )
    executive_service = TonyExecutiveCommandService(command_service, brief_archive=brief_archive)
    return workspace_runtime, executive_service, mission_control_loader


def _event_recorder(workspace_runtime: RuntimeComponents) -> Callable[[dict[str, Any]], None]:
    def record(payload: dict[str, Any]) -> None:
        event_type = str(payload.get("event_type", "proactive_delivery.event"))
        workspace_runtime.event_log.append(
            WorkflowEvent.create(
                event_id=f"evt-{uuid4().hex}",
                run_id=RUN_ID,
                event_type=event_type,
                payload=payload,
                workspace_id=workspace_runtime.workspace.workspace_id,
            )
        )

    return record


def _status_recorder(
    status_store: LatestDeliveryStatusStore, kind: str
) -> Callable[[dict[str, Any]], None]:
    def record(payload: dict[str, Any]) -> None:
        status_store.record(
            DeliveryStatusRecord(
                kind=kind,
                command=str(payload.get("command", "")),
                status=str(payload.get("status", "")),
                recorded_at=str(
                    payload.get("recorded_at", datetime.now(timezone.utc).isoformat())
                ),
                error=payload.get("error"),
            )
        )

    return record


def _combined(*recorders: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], None]:
    def record(payload: dict[str, Any]) -> None:
        for recorder in recorders:
            recorder(payload)

    return record


def run_brief(*, command: str, simulate_transport_failure: bool) -> dict[str, Any]:
    runtime_root = Path(os.getenv("NARRATIIVE_RUNTIME_ROOT", ".runtime")).resolve()
    workspace_id = _workspace_id_from_env()

    try:
        workspace_runtime, executive_service, _ = build_components(
            runtime_root=runtime_root, workspace_id=workspace_id
        )
    except ProactiveBriefConfigurationError as exc:
        return {"status": "configuration_blocked", "command": command, "error": str(exc)}

    status_store = LatestDeliveryStatusStore(
        workspace_runtime.paths.root / "proactive-delivery" / "latest-status.json"
    )
    key_store = FileDeliveryKeyStore(
        workspace_runtime.paths.root / "proactive-delivery" / "brief-delivery-keys.json"
    )
    recorder = _combined(
        _event_recorder(workspace_runtime), _status_recorder(status_store, "brief")
    )

    try:
        telegram = TelegramSender(TelegramConfig.from_env(os.environ))
    except TelegramDeliveryError as exc:
        recorder(
            {
                "event_type": "executive_brief.delivery_blocked",
                "command": command,
                "status": "configuration_blocked",
                "error": str(exc),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"status": "configuration_blocked", "command": command, "error": str(exc)}

    def send(chat_id: str, text: str) -> None:
        if simulate_transport_failure:
            raise TelegramDeliveryError("simulated transport failure")
        telegram.send(chat_id, text)

    service = ProactiveExecutiveDeliveryService(
        execute_command=executive_service.execute,
        send_message=send,
        key_store=key_store,
        record_event=recorder,
        max_attempts=int(os.getenv("TONY_PROACTIVE_MAX_ATTEMPTS", "3")),
    )
    result = service.deliver(
        workspace_id=workspace_id,
        chat_id=telegram.config.default_chat_id,
        command=command,
    )
    return result.to_dict()


def run_escalation(*, simulate_transport_failure: bool) -> dict[str, Any]:
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
    key_store = FileDeliveryKeyStore(
        workspace_runtime.paths.root / "proactive-delivery" / "escalation-keys.json"
    )
    last_sent_store = FileLastEscalationStore(
        workspace_runtime.paths.root / "proactive-delivery" / "escalation-last-sent.json"
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
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"status": "configuration_blocked", "error": str(exc)}

    def send(chat_id: str, text: str) -> None:
        if simulate_transport_failure:
            raise TelegramDeliveryError("simulated transport failure")
        telegram.send(chat_id, text)

    service = MaterialEscalationService(
        mission_control_loader=mission_control_loader,
        send_message=send,
        key_store=key_store,
        last_sent_store=last_sent_store,
        record_event=recorder,
        max_attempts=int(os.getenv("TONY_PROACTIVE_MAX_ATTEMPTS", "3")),
        min_interval_seconds=int(
            os.getenv("TONY_PROACTIVE_ESCALATION_MIN_INTERVAL_SECONDS", "1800")
        ),
    )
    result = service.escalate(
        workspace_id=workspace_id, chat_id=telegram.config.default_chat_id
    )
    return result.to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Trigger Tony's proactive executive delivery: a scheduled or manually "
            "invoked morning/evening brief send, plus material blocker/approval "
            "escalation, through the existing Telegram bridge configuration."
        )
    )
    parser.add_argument("--mode", choices=("brief", "escalation", "both"), default="both")
    parser.add_argument("--command", choices=("morning", "evening"))
    parser.add_argument(
        "--simulate-transport-failure",
        action="store_true",
        help="Force outbound delivery to fail transiently. For smoke validation only.",
    )
    args = parser.parse_args(argv)

    if args.mode in {"brief", "both"} and not args.command:
        parser.error("--command is required when --mode includes 'brief'")

    results: dict[str, Any] = {}
    ok = True

    if args.mode in {"brief", "both"}:
        brief_result = run_brief(
            command=args.command, simulate_transport_failure=args.simulate_transport_failure
        )
        results["brief"] = brief_result
        if brief_result.get("status") in FAILING_STATUSES:
            ok = False

    if args.mode in {"escalation", "both"}:
        escalation_result = run_escalation(
            simulate_transport_failure=args.simulate_transport_failure
        )
        results["escalation"] = escalation_result
        if escalation_result.get("status") in FAILING_STATUSES:
            ok = False

    print(json.dumps({"ok": ok, **results}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
