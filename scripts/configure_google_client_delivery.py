#!/usr/bin/env python3
"""Enable approval-gated client Drive delivery with Gmail notification."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import stat
import tempfile
from pathlib import Path


def install(env_file: Path) -> None:
    env_file = env_file.expanduser()
    if env_file.is_symlink():
        raise ValueError("runtime environment file must not be a symbolic link")
    existing = env_file.read_text(encoding="utf-8") if env_file.is_file() else ""
    name = "TONY_DISPATCH_CLIENT_DELIVERY_MODE"
    rendered = f"{name}={shlex.quote('google_drive_gmail')}"
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
    lines = existing.splitlines()
    indexes = [index for index, line in enumerate(lines) if pattern.match(line)]
    if indexes:
        lines[indexes[0]] = rendered
        for index in reversed(indexes[1:]):
            del lines[index]
    else:
        lines.append(rendered)
    env_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(env_file.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".runtime.env.", dir=env_file.parent)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).rstrip("\n") + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, env_file)
        os.chmod(env_file, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path.home() / ".config" / "narratiive" / "runtime.env",
    )
    args = parser.parse_args()
    install(args.env_file)
    print("Enabled approval-gated client Drive delivery with Gmail notification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
