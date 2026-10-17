from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import stat
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any


SCOPES = (
    "https://www.googleapis.com/auth/calendar.calendars.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
)


def _read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return lines, values


def _replace_secret(lines: list[str], key: str, value: str) -> list[str]:
    replacement = f"{key}={value}\n"
    output: list[str] = []
    replaced = False
    for line in lines:
        if not line.lstrip().startswith(f"{key}="):
            output.append(line)
            continue
        if not replaced:
            output.append(replacement)
            replaced = True
    if not replaced:
        output.append(replacement)
    return output


def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Google returned an invalid token response")
    return payload


def _token_scopes(access_token: str) -> set[str]:
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode(
        {"access_token": access_token}
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {value for value in str(payload.get("scope") or "").split() if value}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reauthorise Narratiive Google Workspace OAuth with the minimum Gmail draft scope"
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--callback-timeout", type=int, default=1200)
    args = parser.parse_args()

    env_path = args.env_file.expanduser().resolve()
    lines, values = _read_env(env_path)
    client_id = values.get("TONY_GOOGLE_CLIENT_ID", "")
    client_secret = values.get("TONY_GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth client credentials are not configured")

    state = secrets.token_urlsafe(32)
    redirect_uri = f"http://127.0.0.1:{args.port}/"
    authorise_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [""])[0] != state:
                result["error"] = "OAuth state mismatch"
                status = 400
            elif query.get("error"):
                result["error"] = query["error"][0]
                status = 400
            else:
                result["code"] = query.get("code", [""])[0]
                status = 200 if result["code"] else 400
            body = b"Authorisation captured. You can return to Codex."
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args: object) -> None:
            return

    print(json.dumps({"authorisation_url": authorise_url, "redirect_uri": redirect_uri}), flush=True)
    server = HTTPServer(("127.0.0.1", args.port), Callback)
    server.timeout = max(60, args.callback_timeout)
    server.handle_request()
    server.server_close()
    if result.get("error"):
        raise RuntimeError(f"Google OAuth failed: {result['error']}")
    if not result.get("code"):
        raise RuntimeError("Google OAuth callback was not received")

    token = _post_form(
        "https://oauth2.googleapis.com/token",
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": result["code"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    refresh_token = str(token.get("refresh_token") or "")
    access_token = str(token.get("access_token") or "")
    if not refresh_token or not access_token:
        raise RuntimeError("Google did not return both access and refresh tokens")
    observed_scopes = _token_scopes(access_token)
    missing = set(SCOPES).difference(observed_scopes)
    unexpected_gmail = {
        value for value in observed_scopes if "/auth/gmail." in value and value not in SCOPES
    }
    if missing or unexpected_gmail:
        raise RuntimeError(
            "Google grant did not match the requested minimum scope set: "
            f"missing={sorted(missing)}, unexpected_gmail={sorted(unexpected_gmail)}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = env_path.with_name(f"{env_path.name}.pre-gmail-compose-{timestamp}")
    shutil.copy2(env_path, backup)
    os.chmod(backup, stat.S_IRUSR | stat.S_IWUSR)
    temporary = env_path.with_name(f".{env_path.name}.oauth.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.writelines(_replace_secret(lines, "TONY_GOOGLE_REFRESH_TOKEN", refresh_token))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(temporary, env_path)
    print(
        json.dumps(
            {
                "status": "reauthorised",
                "scopes": sorted(observed_scopes),
                "backup": str(backup),
                "secrets_printed": False,
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
