#!/usr/bin/env python3
"""Securely configure TikTok OAuth application values without displaying them."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.tiktok_oauth import ProtectedRuntimeEnvironment, TIKTOK_REDIRECT_URI


def install(env_file: Path, *, app_id: str, app_secret: str, advertiser_authorization_url: str) -> None:
    values = {
        "TIKTOK_APP_ID": app_id.strip(),
        "TIKTOK_APP_SECRET": app_secret.strip(),
        "TIKTOK_ADVERTISER_AUTH_URL": advertiser_authorization_url.strip(),
    }
    if any(not value for value in values.values()):
        raise ValueError("TikTok app ID, app secret and advertiser authorization URL are required")
    ProtectedRuntimeEnvironment(env_file).update(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config" / "narratiive" / "runtime.env")
    args = parser.parse_args()
    print(f"Registered Advertiser Redirect URL must be: {TIKTOK_REDIRECT_URI}")
    app_id = getpass.getpass("TikTok app ID (input hidden): ")
    app_secret = getpass.getpass("TikTok app secret (input hidden): ")
    auth_url = getpass.getpass("TikTok advertiser authorization URL (input hidden): ")
    install(args.env_file, app_id=app_id, app_secret=app_secret, advertiser_authorization_url=auth_url)
    print("TikTok OAuth app configuration stored securely; no credential value was displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
