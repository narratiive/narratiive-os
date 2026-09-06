#!/usr/bin/env python3
"""Install Fireflies API configuration in the protected Narratiive runtime env."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shlex
import stat
import tempfile
from pathlib import Path


def install(env_file: Path, api_key: str) -> None:
    key = api_key.strip()
    if not key or "\n" in key or "\r" in key or "\x00" in key:
        raise ValueError("Fireflies API key must be a non-empty single-line value")
    env_file = env_file.expanduser()
    env_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(env_file.parent, 0o700)
    if env_file.is_symlink():
        raise ValueError("runtime environment file must not be a symbolic link")
    try:
        existing = env_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    values = {
        "TONY_DISPATCH_FIREFLIES_MODE": "fireflies_api",
        "TONY_FIREFLIES_API_KEY": key,
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
    descriptor, temporary = tempfile.mkstemp(prefix=".runtime.env.", dir=env_file.parent)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, env_file)
        os.chmod(env_file, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Securely configure the read-only Fireflies adapter.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path.home() / ".config" / "narratiive" / "runtime.env",
        help="Protected Narratiive runtime environment file.",
    )
    args = parser.parse_args()
    api_key = getpass.getpass("Fireflies API key (input hidden): ")
    confirmation = getpass.getpass("Repeat Fireflies API key (input hidden): ")
    if api_key != confirmation:
        raise SystemExit("Fireflies API key entries did not match; nothing was changed.")
    install(args.env_file, api_key)
    print(f"Fireflies runtime configuration installed in {args.env_file.expanduser()} (mode 600).")
    print("Configured TONY_DISPATCH_FIREFLIES_MODE and TONY_FIREFLIES_API_KEY; values were not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
