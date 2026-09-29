#!/usr/bin/env python3
"""Securely configure the Meta OAuth application without displaying secrets."""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.meta_oauth import META_REDIRECT_URI
from runtime.tiktok_oauth import ProtectedRuntimeEnvironment


def install(env_file: Path, *, app_id: str, app_secret: str, graph_version: str) -> None:
    values = {
        "META_APP_ID": app_id.strip(),
        "META_APP_SECRET": app_secret.strip(),
        "META_GRAPH_API_VERSION": graph_version.strip(),
    }
    if not values["META_APP_ID"] or not values["META_APP_SECRET"]:
        raise ValueError("Meta app ID and app secret are required")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", values["META_GRAPH_API_VERSION"]):
        raise ValueError("Meta Graph API version must be explicit, for example v26.0")
    ProtectedRuntimeEnvironment(env_file).update(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config" / "narratiive" / "runtime.env")
    parser.add_argument("--graph-version", default="v26.0")
    args = parser.parse_args()
    print(f"Valid OAuth Redirect URI must be: {META_REDIRECT_URI}")
    app_id = getpass.getpass("Meta app ID (input hidden): ")
    app_secret = getpass.getpass("Meta app secret (input hidden): ")
    install(args.env_file, app_id=app_id, app_secret=app_secret, graph_version=args.graph_version)
    print("Meta OAuth app configuration stored securely; no credential value was displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
