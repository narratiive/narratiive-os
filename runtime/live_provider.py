from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .execution_package import ExecutionPackage
from .http_provider import ProviderTransportError
from .provider import ProviderResponse


class ProviderConfigurationError(RuntimeError):
    """Raised when a live provider is missing safe external configuration."""


@dataclass(frozen=True, slots=True)
class LiveTextProviderConfig:
    provider_id: str
    model_id: str
    endpoint_env: str
    api_key_env: str
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        for field_name in ("provider_id", "model_id", "endpoint_env", "api_key_env"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class EnvironmentTextProviderClient:
    """OpenAI-compatible text adapter whose endpoint and credential stay in the environment."""

    def __init__(self, config: LiveTextProviderConfig) -> None:
        self.config = config

    def generate(self, package: ExecutionPackage) -> ProviderResponse:
        endpoint = os.environ.get(self.config.endpoint_env, "").strip()
        if not endpoint:
            raise ProviderConfigurationError(
                f"live provider endpoint is not configured in {self.config.endpoint_env}"
            )
        _validate_endpoint(endpoint)

        api_key = os.environ.get(self.config.api_key_env, "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                f"live provider credential is not configured in {self.config.api_key_env}"
            )

        body = json.dumps(
            {
                "model": self.config.model_id,
                "messages": [
                    {"role": "system", "content": package.instructions},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "job_id": package.job_id,
                                "run_id": package.run_id,
                                "stage_id": package.stage_id,
                                "input_artifacts": package.input_artifacts,
                                "memory_records": package.memory_records,
                                "confidence_scorecard": package.confidence_scorecard,
                                "context": package.context,
                                "expected_output_type": package.expected_output_type,
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    },
                ],
                "temperature": 0,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "narratiive-os-runtime/1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ProviderTransportError(
                f"live provider returned HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise ProviderTransportError("live provider request failed") from exc

        if status < 200 or status >= 300:
            raise ProviderTransportError(f"live provider returned HTTP {status}")
        content = _response_content(payload)
        return ProviderResponse(
            job_id=package.job_id,
            run_id=package.run_id,
            stage_id=package.stage_id,
            output_type=package.expected_output_type,
            content=content,
            metadata={
                "provider_id": self.config.provider_id,
                "model_id": self.config.model_id,
            },
        )


def _response_content(payload: str) -> str:
    try:
        data = json.loads(payload)
        choices = data["choices"]
        content = choices[0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ProviderTransportError("live provider returned malformed output") from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderTransportError("live provider returned malformed output")
    return content


def _validate_endpoint(endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    if not parsed.netloc or parsed.username or parsed.password:
        raise ProviderConfigurationError("live provider endpoint must be a credential-free URL")
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        return
    raise ProviderConfigurationError(
        "live provider endpoint must use HTTPS unless its hostname is loopback"
    )
