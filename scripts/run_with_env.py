from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def load_env_file(path: Path) -> dict[str, str]:
    resolved = path.expanduser().resolve()
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"environment file must not be accessible by group or others: {resolved}")
    values: dict[str, str] = {}
    for line_number, raw in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid environment entry on line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"invalid environment variable name on line {line_number}")
        values[key] = value.strip()
    return values


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: run_with_env.py ENV_FILE COMMAND [ARG ...]")
    env_file = Path(sys.argv[1])
    command = sys.argv[2:]
    environment = os.environ.copy()
    environment.update(load_env_file(env_file))
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
