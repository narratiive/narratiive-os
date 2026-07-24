from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class SmokeResult:
    check: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "ok": self.ok, "detail": self.detail}


def request_json(url: str, *, payload: dict[str, Any] | None, token: str, timeout: float) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    method = "GET"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    result = json.loads(body)
    if not isinstance(result, dict):
        raise RuntimeError("response was not a JSON object")
    return result


def evaluate_health(payload: dict[str, Any]) -> SmokeResult:
    ok = payload.get("ok") is True and payload.get("status") == "alive"
    detail = f"status={payload.get('status', 'missing')}"
    return SmokeResult("bridge-health", ok, detail)


def evaluate_command(command: str, payload: dict[str, Any]) -> SmokeResult:
    ok = payload.get("ok") is True and isinstance(payload.get("reply") or payload.get("message"), str)
    status = payload.get("status", "missing")
    detail = f"command={payload.get('command', 'missing')}; status={status}"
    return SmokeResult(command.lstrip("/"), ok, detail)


def run(base_url: str, token: str, timeout: float) -> list[SmokeResult]:
    base = base_url.rstrip("/")
    results: list[SmokeResult] = []
    try:
        results.append(evaluate_health(request_json(f"{base}/health", payload=None, token="", timeout=timeout)))
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        results.append(SmokeResult("bridge-health", False, str(exc)))
        return results

    for command in ("/capabilities", "/status"):
        try:
            payload = request_json(
                f"{base}/telegram",
                payload={"message": {"text": command}},
                token=token,
                timeout=timeout,
            )
            results.append(evaluate_command(command, payload))
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            results.append(SmokeResult(command.lstrip("/"), False, str(exc)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the deployed Tony bridge and deterministic command surface.")
    parser.add_argument("--url", default=os.getenv("TONY_BRIDGE_URL", "http://127.0.0.1:8790"))
    parser.add_argument("--token", default=os.getenv("TONY_BRIDGE_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    results = run(args.url, args.token, args.timeout)
    payload = {"ok": all(result.ok for result in results), "checks": [result.to_dict() for result in results]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
