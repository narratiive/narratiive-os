from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_http(name: str, url: str, opener: Callable = urlopen, timeout: float = 5.0) -> CheckResult:
    try:
        with opener(url, timeout=timeout) as response:
            status = int(getattr(response, "status", 0))
            payload = json.loads(response.read().decode("utf-8"))
        ok = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
        detail = f"HTTP {status}; {payload.get('status', 'ok') if isinstance(payload, dict) else 'invalid payload'}"
        return CheckResult(name, ok, detail)
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        return CheckResult(name, False, f"unreachable or invalid response: {exc}")


def check_tony_roundtrip(
    url: str,
    bridge_token: str,
    workspace_id: str,
    client_id: str,
    opener: Callable = urlopen,
    timeout: float = 10.0,
) -> CheckResult:
    if not bridge_token:
        return CheckResult("tony-roundtrip", False, "TONY_BRIDGE_TOKEN is not configured")
    payload = {
        "action": "health",
        "workspace_id": workspace_id,
        "client_id": client_id,
        "command_id": f"acceptance-{uuid4().hex}",
    }
    request = Request(
        url,
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {bridge_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0))
            body = json.loads(response.read().decode("utf-8"))
        ok = status == 200 and isinstance(body, dict) and body.get("ok") is True
        command = body.get("command", "unknown") if isinstance(body, dict) else "invalid payload"
        return CheckResult("tony-roundtrip", ok, f"HTTP {status}; command={command}")
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        return CheckResult("tony-roundtrip", False, f"bridge-to-gateway command failed: {exc}")


def check_secret_file(path: Path) -> CheckResult:
    target = path.expanduser()
    if not target.exists():
        return CheckResult("secret-file", False, f"missing: {target}")
    mode = stat.S_IMODE(target.stat().st_mode)
    if mode != 0o600:
        return CheckResult("secret-file", False, f"unsafe permissions {oct(mode)}; expected 0o600")
    return CheckResult("secret-file", True, f"present with permissions {oct(mode)}")


def read_env_file(path: Path) -> dict[str, str]:
    target = path.expanduser()
    if not target.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def check_launch_agent(label: str, runner: Callable = subprocess.run) -> CheckResult:
    if platform.system() != "Darwin":
        return CheckResult(label, True, "not checked outside macOS")
    domain = f"gui/{os.getuid()}/{label}"
    completed = runner(
        ["launchctl", "print", domain],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if completed.returncode == 0:
        return CheckResult(label, True, "loaded")
    detail = (completed.stderr or completed.stdout or "not loaded").strip()
    return CheckResult(label, False, detail)


def run_checks(
    runtime_url: str,
    bridge_url: str,
    secret_file: Path,
    opener: Callable = urlopen,
    runner: Callable = subprocess.run,
    bridge_command_url: str = "http://127.0.0.1:8790/",
    bridge_token: str = "",
    workspace_id: str = "system",
    client_id: str = "system",
) -> tuple[int, dict]:
    checks = [
        check_secret_file(secret_file),
        check_http("runtime-health", runtime_url, opener=opener),
        check_http("tony-bridge-health", bridge_url, opener=opener),
        check_tony_roundtrip(
            bridge_command_url,
            bridge_token,
            workspace_id,
            client_id,
            opener=opener,
        ),
        check_launch_agent("com.narratiive.runtime", runner=runner),
        check_launch_agent("com.narratiive.tony-http-bridge", runner=runner),
        check_launch_agent("com.narratiive.service-supervisor", runner=runner),
    ]
    ok = all(item.ok for item in checks)
    report = {
        "ok": ok,
        "status": "ready" if ok else "not_ready",
        "checks": [asdict(item) for item in checks],
    }
    return (0 if ok else 1), report


def main() -> None:
    runtime_url = os.getenv("NARRATIIVE_RUNTIME_HEALTH_URL", "http://127.0.0.1:8787/health")
    bridge_url = os.getenv("TONY_BRIDGE_HEALTH_URL", "http://127.0.0.1:8790/health")
    bridge_command_url = os.getenv("TONY_BRIDGE_COMMAND_URL", "http://127.0.0.1:8790/")
    secret_file = Path(os.getenv("NARRATIIVE_ENV_FILE", "~/.config/narratiive/runtime.env"))
    file_env = read_env_file(secret_file)
    bridge_token = os.getenv("TONY_BRIDGE_TOKEN", file_env.get("TONY_BRIDGE_TOKEN", ""))
    workspace_id = os.getenv("NARRATIIVE_HEALTH_WORKSPACE_ID", "system")
    client_id = os.getenv("NARRATIIVE_HEALTH_CLIENT_ID", "system")
    exit_code, report = run_checks(
        runtime_url,
        bridge_url,
        secret_file,
        bridge_command_url=bridge_command_url,
        bridge_token=bridge_token,
        workspace_id=workspace_id,
        client_id=client_id,
    )
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
