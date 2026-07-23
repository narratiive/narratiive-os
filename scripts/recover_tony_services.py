from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from scripts.deploy_tony_runtime import HEALTH_ENDPOINTS, RUNTIME_LABELS, check_health, run_command
from scripts.service_doctor import ServiceDoctor


SERVICE_LABEL_BY_NAME = {
    "runtime-gateway": "com.narratiive.runtime",
    "tony-http-bridge": "com.narratiive.tony-http-bridge",
}
RECOVERY_STATE_PATH = Path("runtime-state") / "recovery.json"


class RecoveryError(RuntimeError):
    """Raised when an automatic service recovery cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    status: str
    restarted_services: tuple[str, ...]
    deployment_healthy: bool
    exit_code_before: int
    exit_code_after: int
    attempted_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "restarted_services": list(self.restarted_services),
            "deployment_healthy": self.deployment_healthy,
            "exit_code_before": self.exit_code_before,
            "exit_code_after": self.exit_code_after,
            "attempted_at": self.attempted_at,
        }


CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _restart_labels(
    labels: Sequence[str],
    *,
    repository_root: Path,
    runner: CommandRunner,
    uid: int | None = None,
) -> tuple[str, ...]:
    user_id = os.getuid() if uid is None else uid
    restarted: list[str] = []
    for label in labels:
        runner(("launchctl", "kickstart", "-k", f"gui/{user_id}/{label}"), repository_root)
        restarted.append(label)
    return tuple(restarted)


def write_recovery_state(
    repository_root: Path,
    result: RecoveryResult,
    *,
    state_path: Path = RECOVERY_STATE_PATH,
) -> Path:
    destination = repository_root / state_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def recover(
    repository_root: Path,
    *,
    doctor: ServiceDoctor | None = None,
    runner: CommandRunner = run_command,
    sleeper: Sleeper = time.sleep,
    gateway_endpoint: str = HEALTH_ENDPOINTS[0],
    bridge_endpoint: str = HEALTH_ENDPOINTS[1],
    deployment_state_path: Path = Path("runtime-state/deployment.json"),
    attempts: int = 8,
    interval_seconds: float = 1.0,
) -> RecoveryResult:
    """Restart only failed services and never auto-deploy a stale revision.

    A stale or missing deployment receipt is intentionally not remediated here:
    updating code is a deployment decision and remains guarded by
    ``deploy_tony_runtime.py --apply``. This command only repairs process-level
    failures for the already-deployed revision.
    """
    root = repository_root.resolve()
    service_doctor = doctor or ServiceDoctor()
    before_code, before = service_doctor.run(
        gateway_endpoint,
        bridge_endpoint,
        repository_root=root,
        deployment_state_path=deployment_state_path,
    )
    deployment = before.get("deployment", {})
    deployment_healthy = bool(deployment.get("healthy", False))
    unhealthy_names = [
        str(service.get("name", ""))
        for service in before.get("services", [])
        if not bool(service.get("healthy", False))
    ]

    if not unhealthy_names:
        status = "healthy" if deployment_healthy else "deployment_action_required"
        result = RecoveryResult(status, (), deployment_healthy, before_code, before_code, _utc_now())
        write_recovery_state(root, result)
        return result

    labels: list[str] = []
    for name in unhealthy_names:
        label = SERVICE_LABEL_BY_NAME.get(name)
        if label is None:
            raise RecoveryError(f"no recovery mapping for unhealthy service: {name}")
        labels.append(label)

    restarted = _restart_labels(labels, repository_root=root, runner=runner)
    after_code = before_code
    after: Mapping[str, object] = before
    for attempt in range(attempts):
        if attempt:
            sleeper(interval_seconds)
        after_code, after = service_doctor.run(
            gateway_endpoint,
            bridge_endpoint,
            repository_root=root,
            deployment_state_path=deployment_state_path,
        )
        services_healthy = all(bool(item.get("healthy", False)) for item in after.get("services", []))
        if services_healthy:
            deployment_after = after.get("deployment", {})
            deployment_after_healthy = bool(deployment_after.get("healthy", False))
            status = "recovered" if deployment_after_healthy else "recovered_deployment_action_required"
            result = RecoveryResult(
                status,
                restarted,
                deployment_after_healthy,
                before_code,
                after_code,
                _utc_now(),
            )
            write_recovery_state(root, result)
            return result

    failed = [
        str(service.get("name", "unknown"))
        for service in after.get("services", [])
        if not bool(service.get("healthy", False))
    ]
    result = RecoveryResult("failed", restarted, deployment_healthy, before_code, after_code, _utc_now())
    write_recovery_state(root, result)
    raise RecoveryError(f"services remained unhealthy after restart: {', '.join(failed)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely restart failed Narratiive OS services without deploying code.",
    )
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform recovery. Without this flag, print the guarded recovery plan only.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.repository.resolve()
    if not args.apply:
        print(json.dumps({
            "status": "ready",
            "mode": "dry-run",
            "repository": str(root),
            "service_mapping": SERVICE_LABEL_BY_NAME,
            "deployment_policy": "never auto-deploy; use deploy_tony_runtime.py --apply",
            "next_command": f"{sys.executable} {Path(__file__).name} --apply",
        }, indent=2, sort_keys=True))
        return 0
    try:
        result = recover(root)
    except (RecoveryError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
