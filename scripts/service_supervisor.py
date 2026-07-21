from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


@dataclass(frozen=True, slots=True)
class RestartResult:
    service: str
    attempted: bool
    succeeded: bool
    return_code: int | None
    error: str = ""


class ServiceSupervisor:
    """Apply deterministic recovery policy to service-doctor exit codes.

    Restart commands are argument arrays, never shell strings. This keeps the
    supervisor safe for launchd use and avoids interpreting environment values
    through a shell.
    """

    def __init__(self, runner: Callable = subprocess.run, timeout_seconds: float = 20.0) -> None:
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def unhealthy_services(doctor_exit_code: int) -> tuple[str, ...]:
        mapping = {
            0: (),
            10: ("runtime-gateway",),
            20: ("tony-http-bridge",),
            30: ("runtime-gateway", "tony-http-bridge"),
        }
        if doctor_exit_code not in mapping:
            raise ValueError(f"unsupported service doctor exit code: {doctor_exit_code}")
        return mapping[doctor_exit_code]

    def restart(self, service: str, command: Sequence[str] | None) -> RestartResult:
        if not command:
            return RestartResult(service, False, False, None, "restart command not configured")
        try:
            completed = self.runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            return RestartResult(
                service=service,
                attempted=True,
                succeeded=completed.returncode == 0,
                return_code=int(completed.returncode),
                error="" if completed.returncode == 0 else "restart command failed",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return RestartResult(service, True, False, None, f"restart error: {exc}")

    def run(self, doctor_exit_code: int, commands: dict[str, Sequence[str] | None]) -> tuple[int, dict]:
        services = self.unhealthy_services(doctor_exit_code)
        results = [self.restart(service, commands.get(service)) for service in services]
        recovered = all(result.succeeded for result in results)
        exit_code = 0 if not services or recovered else 1
        report = {
            "ok": exit_code == 0,
            "status": "healthy" if not services else ("restarted" if recovered else "recovery_failed"),
            "doctor_exit_code": doctor_exit_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "restarts": [self._as_dict(result) for result in results],
        }
        return exit_code, report

    @staticmethod
    def _as_dict(result: RestartResult) -> dict:
        return {
            "service": result.service,
            "attempted": result.attempted,
            "succeeded": result.succeeded,
            "return_code": result.return_code,
            "error": result.error,
        }


def _command_from_env(name: str) -> list[str] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = json.loads(raw)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be a non-empty JSON array of strings")
    return value


def _append_event(path: str, report: dict) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True) + "\n")


def main() -> None:
    doctor_command = _command_from_env("NARRATIIVE_DOCTOR_COMMAND") or [
        os.getenv("PYTHON", "python3"),
        "scripts/service_doctor.py",
    ]
    completed = subprocess.run(
        doctor_command,
        capture_output=True,
        text=True,
        timeout=float(os.getenv("NARRATIIVE_DOCTOR_PROCESS_TIMEOUT_SECONDS", "15")),
        check=False,
    )
    commands = {
        "runtime-gateway": _command_from_env("NARRATIIVE_RUNTIME_RESTART_COMMAND"),
        "tony-http-bridge": _command_from_env("TONY_BRIDGE_RESTART_COMMAND"),
    }
    exit_code, report = ServiceSupervisor(
        timeout_seconds=float(os.getenv("NARRATIIVE_RESTART_TIMEOUT_SECONDS", "20"))
    ).run(completed.returncode, commands)
    event_log = os.getenv("NARRATIIVE_SUPERVISOR_EVENT_LOG", "").strip()
    if event_log:
        _append_event(event_log, report)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
