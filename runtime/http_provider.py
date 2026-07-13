from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .execution_package import ExecutionPackage
from .provider import InvalidProviderResponse, ProviderResponse, provider_response_from_json


class ProviderTransportError(RuntimeError):
    """Raised when the provider endpoint cannot return a usable response."""


@dataclass(frozen=True, slots=True)
class HttpProviderConfig:
    endpoint: str
    timeout_seconds: float = 120.0
    bearer_token: str | None = None
    headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.endpoint.strip():
            raise ValueError("endpoint must not be empty")
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must use http or https")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class HttpProviderClient:
    """Dependency-free JSON transport for provider-neutral execution packages."""

    def __init__(self, config: HttpProviderConfig) -> None:
        self.config = config

    def generate(self, package: ExecutionPackage) -> ProviderResponse:
        body = json.dumps(package.to_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "narratiive-os-runtime/1",
            **dict(self.config.headers or {}),
        }
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"

        request = Request(self.config.endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ProviderTransportError(f"provider returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ProviderTransportError(f"provider request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ProviderTransportError("provider request timed out") from exc

        if status < 200 or status >= 300:
            raise ProviderTransportError(f"provider returned HTTP {status}")
        try:
            return provider_response_from_json(payload)
        except InvalidProviderResponse as exc:
            raise ProviderTransportError("provider returned an invalid response") from exc
