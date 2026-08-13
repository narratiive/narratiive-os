from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path


LABEL = "com.narratiive.telegram-inbound"


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("Telegram inbound LaunchAgent is supported on macOS only")

    repo_root = Path(__file__).resolve().parents[1]
    python_path = (repo_root / ".venv" / "bin" / "python").resolve()
    env_file = Path.home() / ".config" / "narratiive" / "runtime.env"
    launcher = repo_root / "scripts" / "run_with_env.py"

    for path, label in (
        (python_path, "repository Python"),
        (env_file, "runtime environment file"),
        (launcher, "environment launcher"),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    if env_file.stat().st_mode & 0o077:
        raise PermissionError("runtime environment file must use mode 600")

    agents_dir = Path.home() / "Library" / "LaunchAgents"
    log_dir = Path.home() / "Library" / "Logs" / "Narratiive"
    agents_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    target = agents_dir / f"{LABEL}.plist"

    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python_path),
            str(launcher),
            str(env_file),
            str(python_path),
            "-m",
            "openclaw.telegram_inbound",
        ],
        "WorkingDirectory": str(repo_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / f"{LABEL}.out.log"),
        "StandardErrorPath": str(log_dir / f"{LABEL}.err.log"),
    }
    target.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True))

    uid = os.getuid()
    domain = f"gui/{uid}"
    subprocess.run(["launchctl", "bootout", domain, str(target)], check=False, capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=True)
    print(f"installed and started {LABEL}: {target}")


if __name__ == "__main__":
    main()
