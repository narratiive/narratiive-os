#!/usr/bin/env python3
"""Install Higgsfield creative-production configuration without displaying credentials."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shlex
import stat
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.higgsfield_creative_production import higgsfield_credential


def _parse(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in content.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.removeprefix("export ").split("=", 1)
        try:
            values[name.strip()] = shlex.split(value.strip())[0] if value.strip() else ""
        except (ValueError, IndexError):
            values[name.strip()] = value.strip()
    return values


def install(env_file: Path, credential: str) -> None:
    value = credential.strip()
    if not value or ":" not in value or any(marker in value for marker in ("\n", "\r", "\x00")):
        raise ValueError("Higgsfield credential must be the complete KEY_ID:KEY_SECRET value")
    env_file = env_file.expanduser()
    env_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(env_file.parent, 0o700)
    if env_file.is_symlink():
        raise ValueError("runtime environment file must not be a symbolic link")
    try:
        existing = env_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    lines = [
        line for line in existing.splitlines()
        if not re.match(r"^\s*(?:export\s+)?(?:HF_KEY|HF_CREDENTIALS|HF_API_KEY_ID|HF_API_KEY_SECRET)\s*=", line)
    ]
    values = {
        "TONY_DISPATCH_CREATIVE_PRODUCTION_MODE": "higgsfield_api",
        "TONY_HIGGSFIELD_IMAGE_MODEL": "marketing-studio/image",
        "TONY_HIGGSFIELD_VIDEO_MODEL": "bytedance/seedance-2.5/text-to-video",
        "HF_KEY": value,
    }
    for name, configured in values.items():
        rendered = f"{name}={shlex.quote(configured)}"
        pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
        indexes = [index for index, line in enumerate(lines) if pattern.match(line)]
        if indexes:
            lines[indexes[0]] = rendered
            for index in reversed(indexes[1:]):
                del lines[index]
        else:
            lines.append(rendered)
    encoded = ("\n".join(lines).rstrip("\n") + "\n").encode()
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config" / "narratiive" / "runtime.env")
    parser.add_argument("--use-existing", action="store_true", help="Migrate an already installed Higgsfield credential.")
    args = parser.parse_args()
    env_file = args.env_file.expanduser()
    if args.use_existing:
        try:
            existing = _parse(env_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            existing = {}
        credential = higgsfield_credential(existing)
        if not credential:
            raise SystemExit("No complete Higgsfield credential is installed; nothing was changed.")
    else:
        credential = getpass.getpass("Complete Higgsfield API key (input hidden): ")
        confirmation = getpass.getpass("Repeat Higgsfield API key (input hidden): ")
        if credential != confirmation:
            raise SystemExit("Higgsfield key entries did not match; nothing was changed.")
    install(env_file, credential)
    print(f"Higgsfield runtime configuration installed in {env_file} (mode 600).")
    print("The credential was not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
