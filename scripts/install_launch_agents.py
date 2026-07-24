from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentSpec:
    label: str
    arguments: tuple[str, ...]
    keep_alive: bool
    start_interval: int | None = None


def build_specs(repo_root: Path, python_path: Path, env_file: Path) -> tuple[AgentSpec, ...]:
    launcher = repo_root / "scripts" / "run_with_env.py"
    return (
        AgentSpec(
            "com.narratiive.runtime",
            (str(python_path), str(launcher), str(env_file), str(python_path), "-m", "runtime.server"),
            True,
        ),
        AgentSpec(
            "com.narratiive.tony-http-bridge",
            (str(python_path), str(launcher), str(env_file), str(python_path), str(repo_root / "openclaw" / "tony_live_bridge.py")),
            True,
        ),
        AgentSpec(
            "com.narratiive.service-supervisor",
            (str(python_path), str(launcher), str(env_file), str(python_path), str(repo_root / "scripts" / "service_supervisor.py")),
            False,
            60,
        ),
    )


def render_plist(spec: AgentSpec, repo_root: Path, log_dir: Path) -> bytes:
    payload: dict[str, object] = {
        "Label": spec.label,
        "ProgramArguments": list(spec.arguments),
        "WorkingDirectory": str(repo_root),
        "RunAtLoad": True,
        "KeepAlive": spec.keep_alive,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / f"{spec.label}.out.log"),
        "StandardErrorPath": str(log_dir / f"{spec.label}.err.log"),
    }
    if spec.start_interval is not None:
        payload["StartInterval"] = spec.start_interval
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def install(repo_root: Path, python_path: Path, env_file: Path, home: Path, activate: bool) -> list[Path]:
    repo_root = repo_root.expanduser().resolve()
    python_path = python_path.expanduser().resolve()
    env_file = env_file.expanduser().resolve()
    if not (repo_root / "runtime" / "server.py").is_file():
        raise FileNotFoundError("runtime/server.py not found in repository root")
    if not (repo_root / "openclaw" / "tony_live_bridge.py").is_file():
        raise FileNotFoundError("Tony live bridge not found")
    if not python_path.is_file():
        raise FileNotFoundError(f"Python executable not found: {python_path}")
    if not env_file.is_file():
        raise FileNotFoundError(f"environment file not found: {env_file}")
    if env_file.stat().st_mode & 0o077:
        raise PermissionError("environment file must use mode 600")

    agents_dir = home / "Library" / "LaunchAgents"
    log_dir = home / "Library" / "Logs" / "Narratiive"
    agents_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    uid = os.getuid()
    for spec in build_specs(repo_root, python_path, env_file):
        target = agents_dir / f"{spec.label}.plist"
        target.write_bytes(render_plist(spec, repo_root, log_dir))
        written.append(target)
        if activate:
            domain = f"gui/{uid}"
            subprocess.run(["launchctl", "bootout", domain, str(target)], check=False, capture_output=True)
            _run(["launchctl", "bootstrap", domain, str(target)])
    return written


def uninstall(home: Path, deactivate: bool) -> list[Path]:
    agents_dir = home / "Library" / "LaunchAgents"
    uid = os.getuid()
    removed: list[Path] = []
    for label in (
        "com.narratiive.service-supervisor",
        "com.narratiive.tony-http-bridge",
        "com.narratiive.runtime",
    ):
        target = agents_dir / f"{label}.plist"
        if deactivate and target.exists():
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(target)], check=False, capture_output=True)
        if target.exists():
            target.unlink()
            removed.append(target)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Narratiive OS LaunchAgents")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config" / "narratiive" / "runtime.env")
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("launchd installation is supported on macOS only")
    if args.uninstall:
        paths = uninstall(Path.home(), not args.no_activate)
        print(f"removed {len(paths)} LaunchAgents")
    else:
        paths = install(args.repo_root, args.python, args.env_file, Path.home(), not args.no_activate)
        print(f"installed {len(paths)} LaunchAgents")


if __name__ == "__main__":
    main()
