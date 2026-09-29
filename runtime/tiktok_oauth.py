from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from runtime.media_provider_transports import JSONHTTPClient, UrllibJSONHTTPClient


TIKTOK_TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"
TIKTOK_REDIRECT_URI = "https://lushly-spoof-reheat.ngrok-free.dev/webhook/tiktok-media-oauth-callback"
TIKTOK_REQUIRED_SCOPES = frozenset({"44", "100", "200", "210", "220"})
TIKTOK_WRITE_SCOPES = frozenset({"201", "211", "221"})
TIKTOK_ALLOWED_SCOPES = TIKTOK_REQUIRED_SCOPES | TIKTOK_WRITE_SCOPES
TIKTOK_PERMISSION_NAMES = (
    "Read Ad Account Information",
    "Read Campaigns",
    "Create and Update Campaigns — provider capability only; runtime writes remain disabled",
    "Read Ad Groups",
    "Create and Update Ad Groups — provider capability only; runtime writes remain disabled",
    "Read Ads",
    "Create and Update Ads — provider capability only; runtime writes remain disabled",
    "Consolidated Report",
)


class TikTokOAuthError(RuntimeError):
    """A deliberately sanitised OAuth failure safe to return at an HTTP boundary."""


class TikTokOAuthConfigurationError(TikTokOAuthError):
    pass


class TikTokOAuthStateError(TikTokOAuthError):
    pass


@dataclass(frozen=True, slots=True)
class TikTokOAuthResult:
    advertiser_ids: tuple[str, ...]
    granted_scopes: tuple[str, ...]
    provider_capabilities: tuple[str, ...] = ()


def tiktok_provider_capabilities(scopes: set[str] | frozenset[str]) -> tuple[str, ...]:
    mapping = {
        "44": "read_reporting",
        "100": "read_accounts",
        "200": "read_campaigns",
        "201": "manage_campaigns",
        "210": "read_ad_groups",
        "211": "manage_ad_groups",
        "220": "read_ads",
        "221": "manage_ads",
    }
    return tuple(sorted(mapping[scope] for scope in scopes if scope in mapping))


class TikTokOAuthStateStore:
    def __init__(self, path: Path, *, ttl_seconds: int = 600) -> None:
        self.path = path.expanduser()
        self.ttl_seconds = ttl_seconds

    def issue(self) -> str:
        state = secrets.token_urlsafe(32)
        now = int(time.time())
        self._write({
            "state_sha256": hashlib.sha256(state.encode("utf-8")).hexdigest(),
            "issued_at": now,
            "expires_at": now + self.ttl_seconds,
        })
        return state

    def consume(self, supplied: str) -> None:
        if not supplied or len(supplied) > 512:
            raise TikTokOAuthStateError("TikTok OAuth state is missing or invalid")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with os.fdopen(descriptor, "r+", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                if self.path.is_symlink() or not self.path.is_file():
                    raise TikTokOAuthStateError("TikTok OAuth state is missing or already used")
                try:
                    value = json.loads(self.path.read_text(encoding="utf-8"))
                    expected = str(value["state_sha256"])
                    expires_at = int(value["expires_at"])
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise TikTokOAuthStateError("TikTok OAuth state is invalid") from exc
                self.path.unlink()
                actual = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
                if expires_at < int(time.time()):
                    raise TikTokOAuthStateError("TikTok OAuth state has expired")
                if not hmac.compare_digest(actual, expected):
                    raise TikTokOAuthStateError("TikTok OAuth state does not match")
        except TikTokOAuthStateError:
            raise
        except OSError as exc:
            raise TikTokOAuthStateError("TikTok OAuth state could not be validated") from exc

    def _write(self, value: Mapping[str, Any]) -> None:
        if self.path.is_symlink():
            raise TikTokOAuthStateError("TikTok OAuth state path must not be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".tiktok-oauth-state.", dir=self.path.parent)
        try:
            os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(dict(value), handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class ProtectedRuntimeEnvironment:
    _NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def update(self, values: Mapping[str, str]) -> None:
        if self.path.is_symlink():
            raise TikTokOAuthConfigurationError("runtime environment file must not be a symbolic link")
        existing = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        lines = existing.splitlines()
        for name, value in values.items():
            if not self._NAME.fullmatch(name) or "\n" in value or "\r" in value or "\0" in value:
                raise TikTokOAuthConfigurationError("runtime environment value is invalid")
            pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
            indexes = [index for index, line in enumerate(lines) if pattern.match(line)]
            rendered = f"{name}={value}"
            if indexes:
                lines[indexes[0]] = rendered
                for index in reversed(indexes[1:]):
                    del lines[index]
            else:
                lines.append(rendered)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".runtime.env.", dir=self.path.parent)
        try:
            os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines).rstrip("\n") + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class TikTokOAuthService:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        advertiser_authorization_url: str,
        state_store: TikTokOAuthStateStore,
        environment: ProtectedRuntimeEnvironment,
        http: JSONHTTPClient | None = None,
    ) -> None:
        self.app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self.advertiser_authorization_url = advertiser_authorization_url.strip()
        self.state_store = state_store
        self.environment = environment
        self.http = http or UrllibJSONHTTPClient()

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> "TikTokOAuthService":
        return cls(
            app_id=values.get("TIKTOK_APP_ID", ""),
            app_secret=values.get("TIKTOK_APP_SECRET", ""),
            advertiser_authorization_url=values.get("TIKTOK_ADVERTISER_AUTH_URL", ""),
            state_store=TikTokOAuthStateStore(Path(values.get("TIKTOK_OAUTH_STATE_PATH", "~/.config/narratiive/tiktok-oauth-state.json"))),
            environment=ProtectedRuntimeEnvironment(Path(values.get("NARRATIIVE_ENV_FILE", "~/.config/narratiive/runtime.env"))),
        )

    def authorization_url(self) -> str:
        if not self.app_id or not self._app_secret or not self.advertiser_authorization_url:
            raise TikTokOAuthConfigurationError("TikTok OAuth app configuration is incomplete")
        parsed = urllib.parse.urlsplit(self.advertiser_authorization_url)
        if parsed.scheme != "https" or parsed.hostname not in {"business-api.tiktok.com", "ads.tiktok.com"}:
            raise TikTokOAuthConfigurationError("TikTok advertiser authorization URL must use an approved TikTok HTTPS host")
        if parsed.username or parsed.password or parsed.fragment:
            raise TikTokOAuthConfigurationError("TikTok advertiser authorization URL is invalid")
        state = self.state_store.issue()
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key != "state"]
        query.append(("state", state))
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), ""))

    def exchange(self, *, state: str, auth_code: str) -> TikTokOAuthResult:
        if not self.app_id or not self._app_secret:
            raise TikTokOAuthConfigurationError("TikTok OAuth app configuration is incomplete")
        if not auth_code or len(auth_code) > 4096 or "\n" in auth_code or "\r" in auth_code:
            raise TikTokOAuthError("TikTok authorisation code is missing or invalid")
        self.state_store.consume(state)
        try:
            response = self.http.request(
                "POST",
                TIKTOK_TOKEN_URL,
                body={"app_id": self.app_id, "secret": self._app_secret, "auth_code": auth_code},
            )
        except Exception as exc:
            raise TikTokOAuthError("TikTok authorisation-code exchange failed") from exc
        payload = response.payload
        if response.status < 200 or response.status >= 300 or not isinstance(payload, Mapping) or payload.get("code") != 0:
            raise TikTokOAuthError("TikTok rejected the authorisation-code exchange")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise TikTokOAuthError("TikTok returned an invalid token response")
        access_token = str(data.get("access_token") or "").strip()
        scopes = tuple(sorted({str(item) for item in (data.get("scope") or [])}))
        advertiser_ids = tuple(str(item).strip() for item in (data.get("advertiser_ids") or []) if str(item).strip())
        if not access_token:
            raise TikTokOAuthError("TikTok returned an invalid token response")
        granted = set(scopes)
        if not TIKTOK_REQUIRED_SCOPES.issubset(granted):
            raise TikTokOAuthError("TikTok did not grant all required advertising read permissions")
        if granted.difference(TIKTOK_ALLOWED_SCOPES):
            raise TikTokOAuthError("TikTok granted permissions outside the configured provider capability set")
        if not advertiser_ids:
            raise TikTokOAuthError("TikTok returned no authorised advertiser accounts")
        capabilities = tiktok_provider_capabilities(granted)
        values = {
            "TIKTOK_ACCESS_TOKEN": access_token,
            "TIKTOK_GRANTED_SCOPES": ",".join(scopes),
            "TIKTOK_PROVIDER_CAPABILITIES": ",".join(capabilities),
        }
        if len(advertiser_ids) == 1:
            values["TIKTOK_ACCOUNT_ID"] = advertiser_ids[0]
        self.environment.update(values)
        return TikTokOAuthResult(
            advertiser_ids=advertiser_ids,
            granted_scopes=scopes,
            provider_capabilities=capabilities,
        )
