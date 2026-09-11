from __future__ import annotations

import argparse
import json
import os
import plistlib
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


N8N_LABEL = "com.narratiive.n8n"
TUNNEL_LABEL = "com.narratiive.n8n-tunnel"
LEGACY_POLL_LABEL = "com.narratiive.telegram-inbound"
SYSTEM_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    label: str
    arguments: tuple[str, ...]


def validate_webhook_url(value: str) -> tuple[str, str]:
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Telegram webhook URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "Telegram webhook URL must not contain credentials, a query, or a fragment"
        )
    if parsed.path not in {"", "/"}:
        raise ValueError("Telegram webhook URL must be the public n8n base URL, without a path")
    return url.rstrip("/") + "/", parsed.hostname


def _require_secure_env(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"environment file not found: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("environment file must use mode 600")
    keys = {
        line.split("=", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    if "TONY_BRIDGE_TOKEN" not in keys:
        raise ValueError("environment file must define TONY_BRIDGE_TOKEN")


def _assert_openclaw_not_consuming_telegram(path: Path) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    telegram = payload.get("channels", {}).get("telegram", {})
    if isinstance(telegram, dict) and telegram.get("enabled") is True:
        raise RuntimeError(
            "OpenClaw native Telegram is enabled; disable it before assigning the bot webhook to n8n"
        )


def build_specs(
    repo_root: Path,
    python_path: Path,
    env_file: Path,
    node_path: Path,
    n8n_path: Path,
    ngrok_path: Path,
    webhook_url: str,
    *,
    launcher_path: Path | None = None,
) -> tuple[AgentSpec, ...]:
    public_url, hostname = validate_webhook_url(webhook_url)
    launcher = launcher_path or repo_root / "scripts" / "run_with_env.py"
    return (
        AgentSpec(
            TUNNEL_LABEL,
            (str(ngrok_path), "http", f"--url={hostname}", "5678"),
        ),
        AgentSpec(
            N8N_LABEL,
            (
                str(python_path),
                str(launcher),
                str(env_file),
                "/usr/bin/env",
                f"PATH={node_path.parent}:{SYSTEM_PATH}",
                f"WEBHOOK_URL={public_url}",
                "N8N_BLOCK_ENV_ACCESS_IN_NODE=false",
                "N8N_LOG_LEVEL=info",
                str(node_path),
                str(n8n_path),
                "start",
            ),
        ),
    )


def render_plist(spec: AgentSpec, repo_root: Path, log_dir: Path) -> bytes:
    return plistlib.dumps(
        {
            "Label": spec.label,
            "ProgramArguments": list(spec.arguments),
            "WorkingDirectory": str(repo_root),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ProcessType": "Background",
            "StandardOutPath": str(log_dir / f"{spec.label}.out.log"),
            "StandardErrorPath": str(log_dir / f"{spec.label}.err.log"),
        },
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )


def _bootout(domain: str, label: str, plist_path: Path) -> None:
    subprocess.run(
        ("launchctl", "bootout", f"{domain}/{label}"),
        check=False,
        capture_output=True,
    )
    if plist_path.exists():
        subprocess.run(
            ("launchctl", "bootout", domain, str(plist_path)),
            check=False,
            capture_output=True,
        )


def install(
    *,
    repo_root: Path,
    python_path: Path,
    env_file: Path,
    node_path: Path,
    n8n_path: Path,
    ngrok_path: Path,
    webhook_url: str,
    home: Path,
    activate: bool,
    openclaw_config: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.expanduser().resolve()
    python_path = python_path.expanduser().resolve()
    env_file = env_file.expanduser().resolve()
    node_path = node_path.expanduser().resolve()
    n8n_path = n8n_path.expanduser().resolve()
    ngrok_path = ngrok_path.expanduser().resolve()
    config_path = (
        openclaw_config or home / ".openclaw" / "openclaw.json"
    ).expanduser().resolve()

    if not (repo_root / "scripts" / "run_with_env.py").is_file():
        raise FileNotFoundError("scripts/run_with_env.py not found in repository root")
    executables = (
        ("Python", python_path),
        ("Node", node_path),
        ("n8n", n8n_path),
        ("ngrok", ngrok_path),
    )
    for name, path in executables:
        if not path.is_file() or not os.access(path, os.X_OK):
            raise FileNotFoundError(f"{name} executable not found: {path}")
    _require_secure_env(env_file)
    _assert_openclaw_not_consuming_telegram(config_path)
    public_url, _ = validate_webhook_url(webhook_url)

    agents_dir = home / "Library" / "LaunchAgents"
    log_dir = home / "Library" / "Logs" / "Narratiive"
    support_dir = home / "Library" / "Application Support" / "Narratiive"
    agents_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    support_dir.mkdir(parents=True, exist_ok=True)
    installed_launcher = support_dir / "run_with_env.py"
    temporary_launcher = installed_launcher.with_suffix(".py.tmp")
    temporary_launcher.write_bytes((repo_root / "scripts" / "run_with_env.py").read_bytes())
    temporary_launcher.chmod(0o700)
    temporary_launcher.replace(installed_launcher)
    domain = f"gui/{os.getuid()}"

    legacy = agents_dir / f"{LEGACY_POLL_LABEL}.plist"
    if activate:
        _bootout(domain, LEGACY_POLL_LABEL, legacy)
    legacy_removed = legacy.exists()
    if legacy_removed:
        legacy.unlink()

    written: list[str] = []
    for spec in build_specs(
        repo_root,
        python_path,
        env_file,
        node_path,
        n8n_path,
        ngrok_path,
        public_url,
        launcher_path=installed_launcher,
    ):
        target = agents_dir / f"{spec.label}.plist"
        temporary = target.with_suffix(".plist.tmp")
        temporary.write_bytes(render_plist(spec, home, log_dir))
        temporary.replace(target)
        written.append(str(target))
        if activate:
            _bootout(domain, spec.label, target)
            subprocess.run(("launchctl", "bootstrap", domain, str(target)), check=True)

    return {
        "status": "installed",
        "activated": activate,
        "agents": written,
        "environment_launcher": str(installed_launcher),
        "webhook_url": public_url,
        "legacy_poller_removed": legacy_removed,
        "openclaw_native_telegram_enabled": False,
    }


def uninstall(home: Path, *, deactivate: bool) -> list[str]:
    agents_dir = home / "Library" / "LaunchAgents"
    domain = f"gui/{os.getuid()}"
    removed: list[str] = []
    for label in (N8N_LABEL, TUNNEL_LABEL):
        target = agents_dir / f"{label}.plist"
        if deactivate:
            _bootout(domain, label, target)
        if target.exists():
            target.unlink()
            removed.append(str(target))
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the n8n-owned Tony Telegram ingress")
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path.home() / ".config" / "narratiive" / "runtime.env",
    )
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--n8n", type=Path, required=True)
    parser.add_argument("--ngrok", type=Path, required=True)
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("launchd installation is supported on macOS only")
    if args.uninstall:
        print(
            json.dumps(
                {
                    "status": "uninstalled",
                    "agents": uninstall(Path.home(), deactivate=not args.no_activate),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    result = install(
        repo_root=args.repo_root,
        python_path=args.python,
        env_file=args.env_file,
        node_path=args.node,
        n8n_path=args.n8n,
        ngrok_path=args.ngrok,
        webhook_url=args.webhook_url,
        home=Path.home(),
        activate=not args.no_activate,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
