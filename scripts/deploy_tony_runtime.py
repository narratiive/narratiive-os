from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


RUNTIME_LABELS = (
    "com.narratiive.runtime",
    "com.narratiive.tony-http-bridge",
    "com.narratiive.service-supervisor",
)
HEALTH_ENDPOINTS = (
    "http://127.0.0.1:8787/health",
    "http://127.0.0.1:8790/health",
)
DEPLOYMENT_STATE_PATH = Path("runtime-state") / "deployment.json"


class DeploymentError(RuntimeError):
    """Raised when a deployment cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class DeploymentResult:
    previous_revision: str
    deployed_revision: str
    restarted_services: tuple[str, ...]
    health_endpoints: tuple[str, ...]
    rolled_back: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "previous_revision": self.previous_revision,
            "deployed_revision": self.deployed_revision,
            "restarted_services": list(self.restarted_services),
            "health_endpoints": list(self.health_endpoints),
            "rolled_back": self.rolled_back,
        }


CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
HealthChecker = Callable[[str, float], None]


def run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def check_health(endpoint: str, timeout_seconds: float) -> None:
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200))
            payload = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DeploymentError(f"health check failed for {endpoint}: {exc}") from exc
    if status < 200 or status >= 300:
        raise DeploymentError(f"health check failed for {endpoint}: HTTP {status}")
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"health check returned invalid JSON for {endpoint}") from exc
    if not isinstance(data, dict) or data.get("ok") is False:
        raise DeploymentError(f"health check reported unhealthy for {endpoint}")


def _stdout(result: subprocess.CompletedProcess[str]) -> str:
    return str(result.stdout or "").strip()


def _git(runner: CommandRunner, root: Path, *arguments: str) -> str:
    return _stdout(runner(("git", *arguments), root))


def assert_safe_repository(root: Path, runner: CommandRunner = run_command) -> str:
    if not (root / ".git").exists():
        raise DeploymentError(f"not a Git repository: {root}")
    branch = _git(runner, root, "branch", "--show-current")
    if not branch:
        raise DeploymentError("deployment requires a checked-out branch")
    dirty = _git(runner, root, "status", "--porcelain")
    if dirty:
        raise DeploymentError("working tree has uncommitted changes; deployment refused")
    return branch


def restart_services(
    labels: Sequence[str],
    runner: CommandRunner = run_command,
    *,
    cwd: Path,
    uid: int | None = None,
) -> tuple[str, ...]:
    user_id = os.getuid() if uid is None else uid
    restarted: list[str] = []
    for label in labels:
        runner(("launchctl", "kickstart", "-k", f"gui/{user_id}/{label}"), cwd)
        restarted.append(label)
    return tuple(restarted)


def wait_for_health(
    endpoints: Sequence[str],
    checker: HealthChecker = check_health,
    *,
    attempts: int = 10,
    interval_seconds: float = 1.0,
    timeout_seconds: float = 2.0,
) -> None:
    remaining = set(endpoints)
    last_errors: dict[str, str] = {}
    for attempt in range(attempts):
        for endpoint in tuple(remaining):
            try:
                checker(endpoint, timeout_seconds)
            except DeploymentError as exc:
                last_errors[endpoint] = str(exc)
            else:
                remaining.remove(endpoint)
                last_errors.pop(endpoint, None)
        if not remaining:
            return
        if attempt + 1 < attempts:
            time.sleep(interval_seconds)
    detail = "; ".join(last_errors.get(endpoint, endpoint) for endpoint in sorted(remaining))
    raise DeploymentError(f"services did not become healthy: {detail}")


def write_deployment_state(
    root: Path,
    result: DeploymentResult,
    *,
    branch: str,
    state_path: Path = DEPLOYMENT_STATE_PATH,
    now: datetime | None = None,
) -> Path:
    """Persist an atomic receipt proving which revision passed live health checks."""
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {
        "schema_version": 1,
        "status": "healthy",
        "branch": branch,
        "previous_revision": result.previous_revision,
        "deployed_revision": result.deployed_revision,
        "deployed_at": timestamp.isoformat().replace("+00:00", "Z"),
        "restarted_services": list(result.restarted_services),
        "health_endpoints": list(result.health_endpoints),
        "rolled_back": result.rolled_back,
    }
    destination = root / state_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def deploy(
    root: Path,
    *,
    runner: CommandRunner = run_command,
    checker: HealthChecker = check_health,
    labels: Sequence[str] = RUNTIME_LABELS,
    endpoints: Sequence[str] = HEALTH_ENDPOINTS,
) -> DeploymentResult:
    root = root.resolve()
    branch = assert_safe_repository(root, runner)
    previous = _git(runner, root, "rev-parse", "HEAD")

    _git(runner, root, "fetch", "--prune", "origin")
    target = _git(runner, root, "rev-parse", f"origin/{branch}")
    if target == previous:
        restarted = restart_services(labels, runner, cwd=root)
        wait_for_health(endpoints, checker)
        result = DeploymentResult(previous, target, restarted, tuple(endpoints))
        write_deployment_state(root, result, branch=branch)
        return result

    _git(runner, root, "merge", "--ff-only", f"origin/{branch}")
    deployed = _git(runner, root, "rev-parse", "HEAD")

    try:
        runner(
            (
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
            ),
            root,
        )
        restarted = restart_services(labels, runner, cwd=root)
        wait_for_health(endpoints, checker)
    except Exception as exc:
        _git(runner, root, "reset", "--hard", previous)
        try:
            restart_services(labels, runner, cwd=root)
            wait_for_health(endpoints, checker)
        except Exception as rollback_exc:
            raise DeploymentError(
                f"deployment failed and rollback health validation also failed: {rollback_exc}"
            ) from exc
        raise DeploymentError(f"deployment failed; rolled back to {previous}: {exc}") from exc

    result = DeploymentResult(previous, deployed, restarted, tuple(endpoints))
    write_deployment_state(root, result, branch=branch)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely update, test and restart the local Narratiive OS runtime.",
    )
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the deployment. Without this flag, only print the validated plan.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.repository.resolve()
    try:
        branch = assert_safe_repository(root)
        current = _git(run_command, root, "rev-parse", "HEAD")
        if not args.apply:
            print(json.dumps({
                "status": "ready",
                "mode": "dry-run",
                "repository": str(root),
                "branch": branch,
                "current_revision": current,
                "services": list(RUNTIME_LABELS),
                "health_endpoints": list(HEALTH_ENDPOINTS),
                "deployment_state": str(root / DEPLOYMENT_STATE_PATH),
                "next_command": f"{sys.executable} {Path(__file__).name} --apply",
            }, indent=2, sort_keys=True))
            return 0
        result = deploy(root)
        print(json.dumps({
            "status": "deployed",
            "deployment_state": str(root / DEPLOYMENT_STATE_PATH),
            **result.to_dict(),
        }, indent=2, sort_keys=True))
        return 0
    except (DeploymentError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
