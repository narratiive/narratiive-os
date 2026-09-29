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
from runtime.tiktok_oauth import ProtectedRuntimeEnvironment


META_REDIRECT_URI = "https://lushly-spoof-reheat.ngrok-free.dev/webhook/meta-media-oauth-callback"
META_REQUIRED_SCOPES = frozenset({"ads_read"})
META_ALLOWED_SCOPES = frozenset({"ads_read", "public_profile"})
META_FORBIDDEN_SCOPES = frozenset({"ads_management", "business_management"})
META_PERMISSION_NAMES = (
    "ads_read — read advertising accounts, objects and Ads Insights",
)
_GRAPH_VERSION = re.compile(r"^v[0-9]+\.[0-9]+$")


class MetaOAuthError(RuntimeError):
    """A deliberately sanitised OAuth failure safe to return at an HTTP boundary."""


class MetaOAuthConfigurationError(MetaOAuthError):
    pass


class MetaOAuthStateError(MetaOAuthError):
    pass


@dataclass(frozen=True, slots=True)
class MetaOAuthResult:
    account_ids: tuple[str, ...]
    granted_scopes: tuple[str, ...]


class MetaOAuthStateStore:
    def __init__(self, path: Path, *, ttl_seconds: int = 600) -> None:
        self.path = path.expanduser()
        self.ttl_seconds = ttl_seconds

    def issue(self) -> str:
        state = secrets.token_urlsafe(32)
        now = int(time.time())
        self._write(
            {
                "state_sha256": hashlib.sha256(state.encode("utf-8")).hexdigest(),
                "issued_at": now,
                "expires_at": now + self.ttl_seconds,
            }
        )
        return state

    def consume(self, supplied: str) -> None:
        if not supplied or len(supplied) > 512:
            raise MetaOAuthStateError("Meta OAuth state is missing or invalid")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with os.fdopen(descriptor, "r+", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                if self.path.is_symlink() or not self.path.is_file():
                    raise MetaOAuthStateError("Meta OAuth state is missing or already used")
                try:
                    value = json.loads(self.path.read_text(encoding="utf-8"))
                    expected = str(value["state_sha256"])
                    expires_at = int(value["expires_at"])
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise MetaOAuthStateError("Meta OAuth state is invalid") from exc
                self.path.unlink()
                actual = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
                if expires_at < int(time.time()):
                    raise MetaOAuthStateError("Meta OAuth state has expired")
                if not hmac.compare_digest(actual, expected):
                    raise MetaOAuthStateError("Meta OAuth state does not match")
        except MetaOAuthStateError:
            raise
        except OSError as exc:
            raise MetaOAuthStateError("Meta OAuth state could not be validated") from exc

    def _write(self, value: Mapping[str, Any]) -> None:
        if self.path.is_symlink():
            raise MetaOAuthStateError("Meta OAuth state path must not be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".meta-oauth-state.", dir=self.path.parent)
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


class MetaOAuthService:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        graph_version: str,
        state_store: MetaOAuthStateStore,
        environment: ProtectedRuntimeEnvironment,
        http: JSONHTTPClient | None = None,
    ) -> None:
        self.app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self.graph_version = graph_version.strip()
        self.state_store = state_store
        self.environment = environment
        self.http = http or UrllibJSONHTTPClient()

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> "MetaOAuthService":
        return cls(
            app_id=values.get("META_APP_ID", ""),
            app_secret=values.get("META_APP_SECRET", ""),
            graph_version=values.get("META_GRAPH_API_VERSION", ""),
            state_store=MetaOAuthStateStore(
                Path(values.get("META_OAUTH_STATE_PATH", "~/.config/narratiive/meta-oauth-state.json"))
            ),
            environment=ProtectedRuntimeEnvironment(
                Path(values.get("NARRATIIVE_ENV_FILE", "~/.config/narratiive/runtime.env"))
            ),
        )

    def authorization_url(self) -> str:
        self._validate_configuration()
        state = self.state_store.issue()
        return "https://www.facebook.com/{}/dialog/oauth?{}".format(
            self.graph_version,
            urllib.parse.urlencode(
                {
                    "client_id": self.app_id,
                    "redirect_uri": META_REDIRECT_URI,
                    "state": state,
                    "scope": ",".join(sorted(META_REQUIRED_SCOPES)),
                    "response_type": "code",
                    "auth_type": "rerequest",
                }
            ),
        )

    def exchange(self, *, state: str, code: str) -> MetaOAuthResult:
        self._validate_configuration()
        if not code or len(code) > 4096 or "\n" in code or "\r" in code:
            raise MetaOAuthError("Meta authorisation code is missing or invalid")
        self.state_store.consume(state)
        short_token = self._token_request(
            {
                "client_id": self.app_id,
                "client_secret": self._app_secret,
                "redirect_uri": META_REDIRECT_URI,
                "code": code,
            }
        )
        long_token = self._token_request(
            {
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self._app_secret,
                "fb_exchange_token": short_token,
            }
        )
        permissions = self._graph_get("/me/permissions", long_token)
        rows = permissions.get("data")
        if not isinstance(rows, list):
            raise MetaOAuthError("Meta returned an invalid permissions response")
        granted = {
            str(item.get("permission", ""))
            for item in rows
            if isinstance(item, Mapping) and item.get("status") == "granted"
        }
        if not META_REQUIRED_SCOPES.issubset(granted):
            raise MetaOAuthError("Meta did not grant all approved Phase 1 read permissions")
        if granted.intersection(META_FORBIDDEN_SCOPES):
            raise MetaOAuthError("Meta granted a permission prohibited in Phase 1")
        unexpected = granted.difference(META_ALLOWED_SCOPES)
        if unexpected:
            raise MetaOAuthError("Meta granted permissions outside the approved Phase 1 set")

        accounts = self._graph_data(
            "/me/adaccounts",
            long_token,
            fields="id,account_id,name,account_status,currency,timezone_name",
            limit="100",
        )
        account_ids = tuple(
            str(item.get("account_id") or str(item.get("id", "")).removeprefix("act_")).strip()
            for item in accounts
            if str(item.get("account_id") or item.get("id") or "").strip()
        )
        if not account_ids:
            raise MetaOAuthError("Meta returned no authorised advertising accounts")
        values = {"META_ACCESS_TOKEN": long_token}
        if len(accounts) == 1:
            account = accounts[0]
            values.update(
                {
                    "META_ACCOUNT_ID": account_ids[0],
                    "META_TIMEZONE": str(account.get("timezone_name") or "").strip(),
                    "META_CURRENCY": str(account.get("currency") or "").strip().upper(),
                }
            )
        self.environment.update({key: value for key, value in values.items() if value})
        return MetaOAuthResult(
            account_ids=account_ids,
            granted_scopes=tuple(sorted(granted.intersection(META_ALLOWED_SCOPES))),
        )

    def _validate_configuration(self) -> None:
        if not self.app_id or not self._app_secret or not _GRAPH_VERSION.fullmatch(self.graph_version):
            raise MetaOAuthConfigurationError("Meta OAuth app configuration is incomplete")

    def _token_request(self, query: Mapping[str, str]) -> str:
        try:
            response = self.http.request(
                "GET",
                f"https://graph.facebook.com/{self.graph_version}/oauth/access_token",
                query=query,
            )
        except Exception as exc:
            raise MetaOAuthError("Meta authorisation-code exchange failed") from exc
        payload = response.payload
        if response.status < 200 or response.status >= 300 or not isinstance(payload, Mapping):
            raise MetaOAuthError("Meta rejected the authorisation-code exchange")
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise MetaOAuthError("Meta returned an invalid token response")
        return token

    def _graph_get(self, path: str, token: str, **query: str) -> Mapping[str, Any]:
        proof = hmac.new(
            self._app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        try:
            response = self.http.request(
                "GET",
                f"https://graph.facebook.com/{self.graph_version}{path}",
                query={**query, "access_token": token, "appsecret_proof": proof},
            )
        except Exception as exc:
            raise MetaOAuthError("Meta credential verification failed") from exc
        if response.status < 200 or response.status >= 300 or not isinstance(response.payload, Mapping):
            raise MetaOAuthError("Meta credential verification failed")
        return response.payload

    def _graph_data(self, path: str, token: str, **query: str) -> list[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        after = ""
        for _ in range(100):
            page_query = dict(query)
            if after:
                page_query["after"] = after
            payload = self._graph_get(path, token, **page_query)
            data = payload.get("data")
            if not isinstance(data, list):
                raise MetaOAuthError("Meta returned an invalid advertising-account response")
            rows.extend(item for item in data if isinstance(item, Mapping))
            paging = payload.get("paging")
            cursors = paging.get("cursors") if isinstance(paging, Mapping) else None
            next_after = str(cursors.get("after") or "") if isinstance(cursors, Mapping) else ""
            has_next = bool(paging.get("next")) if isinstance(paging, Mapping) else False
            if not has_next:
                return rows
            if not next_after or next_after == after:
                raise MetaOAuthError("Meta returned invalid advertising-account pagination")
            after = next_after
        raise MetaOAuthError("Meta advertising-account pagination exceeded the safety limit")
