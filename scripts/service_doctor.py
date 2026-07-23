from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


@dataclass(frozen=True, slots=True)
class ServiceCheck:
    name: str
    endpoint: str
    healthy: bool
    status_code: int | None
    error: str = ""


@dataclass(frozen=True, slots=True)
class DeploymentCheck:
    healthy: bool
    deployed_revision: str = ""
    current_revision: str = ""
    deployed_at: str = ""
    error: str = ""


class ServiceDoctor:
    """Independent liveness and deployment checks for Narratiive OS.

    Exit codes are additive and stable for launchd or another supervisor:
      0  healthy
      10 runtime gateway unhealthy
      20 Tony bridge unhealthy
      40 deployment receipt missing, invalid or stale

    Combined failures add their codes, for example 70 means all three checks
    failed. This preserves the original service-only exit codes while making a
    stale live deployment immediately distinguishable from a network timeout.
    """

    def __init__(
        self,
        opener: Callable = urlopen,
        timeout_seconds: float = 3.0,
        revision_reader: Callable[[Path], str] | None = None,
    ) -> None:
        self.opener = opener
        self.timeout_seconds = timeout_seconds
        self.revision_reader = revision_reader or self._read_git_revision

    def check(self, name: str, endpoint: str) -> ServiceCheck:
        try:
            with self.opener(endpoint, timeout=self.timeout_seconds) as response:
                status_code = int(getattr(response, "status", response.getcode()))
                raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
            healthy = status_code == 200 and bool(payload.get("ok"))
            return ServiceCheck(
                name=name,
                endpoint=endpoint,
                healthy=healthy,
                status_code=status_code,
                error="" if healthy else "unhealthy response",
            )
        except HTTPError as exc:
            return ServiceCheck(name, endpoint, False, int(exc.code), f"http error: {exc.code}")
        except (URLError, TimeoutError, OSError) as exc:
            return ServiceCheck(name, endpoint, False, None, f"connection error: {exc}")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return ServiceCheck(name, endpoint, False, None, f"invalid response: {exc}")

    def check_deployment(self, repository_root: Path, state_path: Path) -> DeploymentCheck:
        receipt_path = state_path if state_path.is_absolute() else repository_root / state_path
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return DeploymentCheck(False, error=f"deployment receipt missing: {receipt_path}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return DeploymentCheck(False, error=f"deployment receipt invalid: {exc}")

        if not isinstance(payload, dict):
            return DeploymentCheck(False, error="deployment receipt must be a JSON object")
        deployed = str(payload.get("deployed_revision", "")).strip()
        deployed_at = str(payload.get("deployed_at", "")).strip()
        status = str(payload.get("status", "")).strip()
        if not deployed or not deployed_at or status != "healthy":
            return DeploymentCheck(False, deployed_revision=deployed, deployed_at=deployed_at, error="deployment receipt is incomplete or unhealthy")

        try:
            current = self.revision_reader(repository_root).strip()
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            return DeploymentCheck(False, deployed_revision=deployed, deployed_at=deployed_at, error=f"current revision unavailable: {exc}")
        if not current:
            return DeploymentCheck(False, deployed_revision=deployed, deployed_at=deployed_at, error="current revision unavailable")
        if deployed != current:
            return DeploymentCheck(
                False,
                deployed_revision=deployed,
                current_revision=current,
                deployed_at=deployed_at,
                error=f"live deployment is stale: deployed {deployed[:12]}, repository {current[:12]}",
            )
        return DeploymentCheck(True, deployed, current, deployed_at)

    def run(
        self,
        gateway_endpoint: str,
        bridge_endpoint: str,
        *,
        repository_root: Path | None = None,
        deployment_state_path: Path = Path("runtime-state/deployment.json"),
    ) -> tuple[int, dict]:
        gateway = self.check("runtime-gateway", gateway_endpoint)
        bridge = self.check("tony-http-bridge", bridge_endpoint)
        deployment = self.check_deployment(repository_root, deployment_state_path) if repository_root else None
        exit_code = self.exit_code(
            gateway.healthy,
            bridge.healthy,
            deployment.healthy if deployment is not None else True,
        )
        report = {
            "ok": exit_code == 0,
            "status": "healthy" if exit_code == 0 else "degraded",
            "exit_code": exit_code,
            "services": [self._as_dict(gateway), self._as_dict(bridge)],
        }
        if deployment is not None:
            report["deployment"] = self._deployment_as_dict(deployment)
        return exit_code, report

    @staticmethod
    def exit_code(gateway_healthy: bool, bridge_healthy: bool, deployment_healthy: bool = True) -> int:
        return (0 if gateway_healthy else 10) + (0 if bridge_healthy else 20) + (0 if deployment_healthy else 40)

    @staticmethod
    def _as_dict(check: ServiceCheck) -> dict:
        return {
            "name": check.name,
            "endpoint": check.endpoint,
            "healthy": check.healthy,
            "status_code": check.status_code,
            "error": check.error,
        }

    @staticmethod
    def _deployment_as_dict(check: DeploymentCheck) -> dict:
        return {
            "name": "deployment-state",
            "healthy": check.healthy,
            "deployed_revision": check.deployed_revision,
            "current_revision": check.current_revision,
            "deployed_at": check.deployed_at,
            "error": check.error,
        }

    @staticmethod
    def _read_git_revision(repository_root: Path) -> str:
        return subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


def main() -> None:
    gateway_endpoint = os.getenv("NARRATIIVE_GATEWAY_HEALTH_ENDPOINT", "http://127.0.0.1:8787/health")
    bridge_endpoint = os.getenv("TONY_BRIDGE_HEALTH_ENDPOINT", "http://127.0.0.1:8790/health")
    timeout_seconds = float(os.getenv("NARRATIIVE_DOCTOR_TIMEOUT_SECONDS", "3"))
    repository_root = Path(os.getenv("NARRATIIVE_REPOSITORY_ROOT", Path(__file__).resolve().parents[1]))
    deployment_state_path = Path(os.getenv("TONY_DEPLOYMENT_STATE", "runtime-state/deployment.json"))
    exit_code, report = ServiceDoctor(timeout_seconds=timeout_seconds).run(
        gateway_endpoint,
        bridge_endpoint,
        repository_root=repository_root,
        deployment_state_path=deployment_state_path,
    )
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
