from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TonyAgentGatewayError(RuntimeError):
    """Raised when Tony cannot obtain a trustworthy agent response."""


@dataclass(frozen=True, slots=True)
class TonyAgentGatewayConfig:
    responses_url: str = "http://127.0.0.1:18789/v1/responses"
    agent_id: str = "tony"
    gateway_token: str = ""
    session_key: str = "narratiive:tony:telegram"
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TonyAgentGatewayConfig":
        base = str(env.get("OPENCLAW_GATEWAY_URL", "")).strip().rstrip("/") or "http://127.0.0.1:18789"
        responses_url = str(env.get("TONY_OPENCLAW_RESPONSES_URL", "")).strip() or f"{base}/v1/responses"
        return cls(
            responses_url=responses_url,
            agent_id=str(env.get("TONY_OPENCLAW_AGENT_ID", "")).strip() or "tony",
            gateway_token=str(env.get("OPENCLAW_GATEWAY_TOKEN", "")).strip(),
            session_key=str(env.get("TONY_OPENCLAW_SESSION_KEY", "")).strip() or "narratiive:tony:telegram",
            timeout_seconds=float(env.get("TONY_OPENCLAW_TIMEOUT_SECONDS", "120")),
        )


class TonyAgentGateway:
    """Thin natural-language ingress for Tony 2.0.

    Human language is interpreted by OpenClaw's normal agent run, not by Python
    phrase matching. Explicit slash commands remain available to the legacy
    deterministic command surface during migration.
    """

    def __init__(self, config: TonyAgentGatewayConfig) -> None:
        self.config = config

    @staticmethod
    def is_system_command(text: str) -> bool:
        return text.lstrip().startswith("/")

    def converse(self, text: str) -> str:
        message = str(text).strip()
        if not message:
            raise TonyAgentGatewayError("message is required")
        if self.is_system_command(message):
            raise TonyAgentGatewayError("slash commands belong to the deterministic command surface")

        body = json.dumps(
            {
                "model": f"openclaw/{self.config.agent_id}",
                "input": message,
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-openclaw-agent-id": self.config.agent_id,
            "x-openclaw-session-key": self.config.session_key,
            "x-openclaw-message-channel": "telegram",
        }
        if self.config.gateway_token:
            headers["Authorization"] = f"Bearer {self.config.gateway_token}"
        request = Request(self.config.responses_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise TonyAgentGatewayError(f"OpenClaw returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TonyAgentGatewayError(f"OpenClaw agent request failed: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TonyAgentGatewayError("OpenClaw returned invalid JSON") from exc
        reply = self._extract_text(payload)
        if not reply:
            raise TonyAgentGatewayError("OpenClaw returned no conversational response")
        return reply

    @staticmethod
    def _extract_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = payload.get("output")
        if not isinstance(output, list):
            return ""
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()


def build_gateway() -> TonyAgentGateway:
    return TonyAgentGateway(TonyAgentGatewayConfig.from_env(os.environ))
