from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen


class VoiceboxError(RuntimeError):
    """Base error for the optional Voicebox integration."""


class VoiceboxConfigurationError(VoiceboxError):
    """Raised when Voicebox runtime configuration is unsafe or invalid."""


class VoiceboxUnavailableError(VoiceboxError):
    """Raised when Voicebox cannot return a usable response."""


class VoiceboxGenerationError(VoiceboxError):
    """Raised when a Voicebox generation reaches a failed state."""


def _parse_bool(value: str, *, name: str) -> bool:
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off", ""}:
        return False
    raise VoiceboxConfigurationError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class VoiceboxConfig:
    """Opt-in configuration for a separately managed Voicebox service."""

    enabled: bool = False
    base_url: str = "http://127.0.0.1:17493"
    timeout_seconds: float = 10.0
    client_id: str = "narratiive-os"
    default_profile: str | None = None
    default_engine: str | None = None
    allow_remote: bool = False
    bearer_token: str | None = None
    max_download_bytes: int = 100 * 1024 * 1024

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise VoiceboxConfigurationError("Voicebox URL must be an http(s) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise VoiceboxConfigurationError(
                "Voicebox URL must not contain credentials, a query, or a fragment"
            )
        if parsed.path not in {"", "/"}:
            raise VoiceboxConfigurationError("Voicebox URL must not contain a path")
        loopback_hosts = {"127.0.0.1", "::1", "localhost"}
        if parsed.hostname.lower() not in loopback_hosts:
            if not self.allow_remote:
                raise VoiceboxConfigurationError(
                    "Voicebox is unauthenticated upstream; remote endpoints require "
                    "NARRATIIVE_VOICEBOX_ALLOW_REMOTE=true and an HTTPS reverse proxy"
                )
            if parsed.scheme != "https":
                raise VoiceboxConfigurationError("Remote Voicebox endpoints must use HTTPS")
            if not self.bearer_token:
                raise VoiceboxConfigurationError(
                    "Remote Voicebox endpoints require a bearer token enforced by the reverse proxy"
                )
        if self.timeout_seconds <= 0:
            raise VoiceboxConfigurationError("Voicebox timeout must be positive")
        if not self.client_id.strip() or len(self.client_id) > 64:
            raise VoiceboxConfigurationError("Voicebox client ID must contain 1-64 characters")
        if self.max_download_bytes <= 0:
            raise VoiceboxConfigurationError("Voicebox download limit must be positive")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "VoiceboxConfig":
        active_env = os.environ if env is None else env
        timeout_raw = active_env.get("NARRATIIVE_VOICEBOX_TIMEOUT_SECONDS", "10").strip()
        download_raw = active_env.get("NARRATIIVE_VOICEBOX_MAX_DOWNLOAD_BYTES", str(100 * 1024 * 1024)).strip()
        try:
            timeout_seconds = float(timeout_raw)
            max_download_bytes = int(download_raw)
        except ValueError as exc:
            raise VoiceboxConfigurationError(
                "Voicebox timeout and download limit must be numeric"
            ) from exc

        default_profile = active_env.get("NARRATIIVE_VOICEBOX_PROFILE", "").strip() or None
        default_engine = active_env.get("NARRATIIVE_VOICEBOX_ENGINE", "").strip() or None
        return cls(
            enabled=_parse_bool(
                active_env.get("NARRATIIVE_VOICEBOX_ENABLED", "false"),
                name="NARRATIIVE_VOICEBOX_ENABLED",
            ),
            base_url=active_env.get(
                "NARRATIIVE_VOICEBOX_URL", "http://127.0.0.1:17493"
            ).strip(),
            timeout_seconds=timeout_seconds,
            client_id=active_env.get(
                "NARRATIIVE_VOICEBOX_CLIENT_ID", "narratiive-os"
            ).strip(),
            default_profile=default_profile,
            default_engine=default_engine,
            allow_remote=_parse_bool(
                active_env.get("NARRATIIVE_VOICEBOX_ALLOW_REMOTE", "false"),
                name="NARRATIIVE_VOICEBOX_ALLOW_REMOTE",
            ),
            bearer_token=active_env.get("NARRATIIVE_VOICEBOX_BEARER_TOKEN", "").strip()
            or None,
            max_download_bytes=max_download_bytes,
        )


class VoiceboxClient:
    """Small dependency-free client for Voicebox's REST automation surface.

    Voicebox remains a separate process and data store. This client does not
    register it as a Narratiive provider, Tony capability, or approval bypass.
    """

    def __init__(
        self,
        config: VoiceboxConfig,
        *,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.config = config
        self._opener = opener

    def health(self) -> Mapping[str, Any]:
        return self._request_object("GET", "/health")

    def list_profiles(self) -> tuple[Mapping[str, Any], ...]:
        payload = self._request_json("GET", "/profiles")
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise VoiceboxUnavailableError("Voicebox returned an invalid profiles response")
        return tuple(payload)

    def speak(
        self,
        text: str,
        *,
        profile: str | None = None,
        engine: str | None = None,
        language: str | None = None,
        personality: bool | None = None,
    ) -> Mapping[str, Any]:
        if not text.strip():
            raise ValueError("Voicebox text must not be empty")
        if len(text) > 10_000:
            raise ValueError("Voicebox /speak accepts at most 10,000 characters")

        payload: dict[str, Any] = {"text": text}
        resolved_profile = profile or self.config.default_profile
        resolved_engine = engine or self.config.default_engine
        if resolved_profile:
            payload["profile"] = resolved_profile
        if resolved_engine:
            payload["engine"] = resolved_engine
        if language:
            payload["language"] = language
        if personality is not None:
            payload["personality"] = personality
        return self._request_object("POST", "/speak", payload)

    def generation(self, generation_id: str) -> Mapping[str, Any]:
        safe_id = self._safe_generation_id(generation_id)
        return self._request_object("GET", f"/history/{safe_id}")

    def wait_for_generation(
        self,
        generation_id: str,
        *,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
    ) -> Mapping[str, Any]:
        if timeout_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("Voicebox wait and poll intervals must be positive")
        deadline = time.monotonic() + timeout_seconds
        while True:
            generation = self.generation(generation_id)
            status = str(generation.get("status", "")).lower()
            if status == "completed":
                return generation
            if status == "failed":
                detail = str(generation.get("error") or "unknown generation error")
                raise VoiceboxGenerationError(detail[:500])
            if time.monotonic() >= deadline:
                raise VoiceboxUnavailableError(
                    f"Voicebox generation {generation_id} did not finish before timeout"
                )
            time.sleep(poll_interval_seconds)

    def download_audio(self, generation_id: str) -> bytes:
        safe_id = self._safe_generation_id(generation_id)
        return self._request_bytes("GET", f"/audio/{safe_id}")

    def _safe_generation_id(self, generation_id: str) -> str:
        value = generation_id.strip()
        if not value or len(value) > 128:
            raise ValueError("Voicebox generation ID must contain 1-128 characters")
        return quote(value, safe="")

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        raw = self._request(method, path, payload)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VoiceboxUnavailableError("Voicebox returned invalid JSON") from exc

    def _request_object(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        result = self._request_json(method, path, payload)
        if not isinstance(result, dict):
            raise VoiceboxUnavailableError("Voicebox returned an invalid object response")
        return result

    def _request_bytes(self, method: str, path: str) -> bytes:
        return self._request(method, path, None)

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
    ) -> bytes:
        if not self.config.enabled:
            raise VoiceboxConfigurationError(
                "Voicebox is disabled; set NARRATIIVE_VOICEBOX_ENABLED=true to opt in"
            )
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "narratiive-os-voicebox/1",
            "X-Voicebox-Client-Id": self.config.client_id,
        }
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        request = Request(
            urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/")),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except ValueError as exc:
                        raise VoiceboxUnavailableError(
                            "Voicebox returned an invalid Content-Length"
                        ) from exc
                    if declared_length > self.config.max_download_bytes:
                        raise VoiceboxUnavailableError(
                            "Voicebox response exceeds the download limit"
                        )
                raw = response.read(self.config.max_download_bytes + 1)
        except HTTPError as exc:
            detail = exc.read(500).decode("utf-8", errors="replace")
            raise VoiceboxUnavailableError(
                f"Voicebox returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise VoiceboxUnavailableError(f"Voicebox request failed: {reason}") from exc
        if status < 200 or status >= 300:
            raise VoiceboxUnavailableError(f"Voicebox returned HTTP {status}")
        if len(raw) > self.config.max_download_bytes:
            raise VoiceboxUnavailableError("Voicebox response exceeds the download limit")
        return raw
