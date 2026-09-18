#!/usr/bin/env python3
"""Install validated local presentation-runtime paths for Tony's document worker."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import stat
import tempfile
from pathlib import Path


def install(
    env_file: Path,
    *,
    node: Path,
    node_modules: Path,
    skill_dir: Path,
    python: Path,
) -> None:
    resolved = {
        "NARRATIIVE_PRESENTATION_NODE": node.expanduser().resolve(),
        "NARRATIIVE_PRESENTATION_NODE_MODULES": node_modules.expanduser().resolve(),
        "NARRATIIVE_PRESENTATION_SKILL_DIR": skill_dir.expanduser().resolve(),
        "NARRATIIVE_PRESENTATION_PYTHON": python.expanduser().resolve(),
    }
    for name in ("NARRATIIVE_PRESENTATION_NODE", "NARRATIIVE_PRESENTATION_PYTHON"):
        if not resolved[name].is_file():
            raise ValueError(f"{name} must point to an existing file")
    for name in ("NARRATIIVE_PRESENTATION_NODE_MODULES", "NARRATIIVE_PRESENTATION_SKILL_DIR"):
        if not resolved[name].is_dir():
            raise ValueError(f"{name} must point to an existing directory")

    target = env_file.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    if target.is_symlink():
        raise ValueError("runtime environment file must not be a symbolic link")
    try:
        existing = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    values = {
        "NARRATIIVE_DOCUMENT_WORKER_MODE": "local_artifact_tool",
        **{name: str(path) for name, path in resolved.items()},
    }
    lines = existing.splitlines()
    for name, value in values.items():
        rendered = f"{name}={shlex.quote(value)}"
        pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
        indexes = [index for index, line in enumerate(lines) if pattern.match(line)]
        if indexes:
            lines[indexes[0]] = rendered
            for index in reversed(indexes[1:]):
                del lines[index]
        else:
            lines.append(rendered)
    encoded = ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".runtime.env.", dir=target.parent)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Tony's local Blueprint document worker.")
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config" / "narratiive" / "runtime.env")
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--node-modules", type=Path, required=True)
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    args = parser.parse_args()
    install(
        args.env_file,
        node=args.node,
        node_modules=args.node_modules,
        skill_dir=args.skill_dir,
        python=args.python,
    )
    print(f"Document worker configuration installed in {args.env_file.expanduser()} (mode 600).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
