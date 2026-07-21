from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
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


class ServiceDoctor:
    """Independent liveness checks for Narratiive OS services.

    Exit codes are intentionally stable for launchd or another supervisor:
      0  all services healthy
      10 runtime gateway unhealthy
      20 Tony bridge unhealthy
      30 both services unhealthy
    """

    def __init__(self, opener: Callable = urlopen, timeout_seconds: float = 3.0) -> None:
        self.opener = opener
        self.timeout_seconds = timeout_seconds

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

    def run(self, gateway_endpoint: str, bridge_endpoint: str) -> tuple[int, dict]:
        gateway = self.check("runtime-gateway", gateway_endpoint)
        bridge = self.check("tony-http-bridge", bridge_endpoint)
        exit_code = self.exit_code(gateway.healthy, bridge.healthy)
        return exit_code, {
            "ok": exit_code == 0,
            "status": "healthy" if exit_code == 0 else "degraded",
            "exit_code": exit_code,
            "services": [self._as_dict(gateway), self._as_dict(bridge)],
        }

    @staticmethod
    def exit_code(gateway_healthy: bool, bridge_healthy: bool) -> int:
        if gateway_healthy and bridge_healthy:
            return 0
        if not gateway_healthy and not bridge_healthy:
            return 30
        return 10 if not gateway_healthy else 20

    @staticmethod
    def _as_dict(check: ServiceCheck) -> dict:
        return {
            "name": check.name,
            "endpoint": check.endpoint,
            "healthy": check.healthy,
            "status_code": check.status_code,
            "error": check.error,
        }


def main() -> None:
    gateway_endpoint = os.getenv("NARRATIIVE_GATEWAY_HEALTH_ENDPOINT", "http://127.0.0.1:8787/health")
    bridge_endpoint = os.getenv("TONY_BRIDGE_HEALTH_ENDPOINT", "http://127.0.0.1:8790/health")
    timeout_seconds = float(os.getenv("NARRATIIVE_DOCTOR_TIMEOUT_SECONDS", "3"))
    exit_code, report = ServiceDoctor(timeout_seconds=timeout_seconds).run(gateway_endpoint, bridge_endpoint)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
