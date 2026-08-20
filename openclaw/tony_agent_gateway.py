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
    user_id: str = ""
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TonyAgentGatewayConfig":
        base = str(env.get("OPENCLAW_GATEWAY_URL", "")).strip().rstrip("/") or "http://127.0.0.1:18789"
        responses_url = str(env.get("TONY_OPENCLAW_RESPONSES_URL", "")).strip() or f"{base}/v1/responses"
        session_key = str(env.get("TONY_OPENCLAW_SESSION_KEY", "")).strip() or "narratiive:tony:telegram"
        return cls(
            responses_url=responses_url,
            agent_id=str(env.get("TONY_OPENCLAW_AGENT_ID", "")).strip() or "tony",
            gateway_token=str(env.get("OPENCLAW_GATEWAY_TOKEN", "")).strip(),
            session_key=session_key,
            user_id=str(env.get("TONY_OPENCLAW_USER_ID", "")).strip() or session_key,
            timeout_seconds=float(env.get("TONY_OPENCLAW_TIMEOUT_SECONDS", "120")),
        )


class TonyAgentGateway:
    """Thin natural-language ingress for Tony 2.0.

    OpenClaw owns semantic interpretation, durable conversation, specialist orchestration,
    and the native agent/tool loop. Narratiive OS is exposed to Tony through OpenClaw's
    bounded control-plane plugin, where permissions, approvals and evidence are enforced.

    This adapter deliberately does not mirror Narratiive tools as client-side function
    definitions and does not translate model-selected tools back into legacy commands.
    """

    def __init__(self, config: TonyAgentGatewayConfig) -> None:
        self.config = config

    @property
    def stable_user_id(self) -> str:
        """Return the OpenResponses user key that makes independent turns share one agent session."""
        return self.config.user_id.strip() or self.config.session_key.strip()

    @staticmethod
    def is_system_command(text: str) -> bool:
        return text.lstrip().startswith("/")

    def converse(self, text: str) -> str:
        message = str(text).strip()
        if not message:
            raise TonyAgentGatewayError("message is required")
        if self.is_system_command(message):
            raise TonyAgentGatewayError("slash commands belong to the deterministic command surface")
        if not self.stable_user_id:
            raise TonyAgentGatewayError("a stable OpenClaw user/session key is required")

        request_body: dict[str, Any] = {
            "model": f"openclaw/{self.config.agent_id}",
            "user": self.stable_user_id,
            "input": message,
            "instructions": (
                "You are Tony, Narratiive's Chief of Staff. Converse naturally and preserve conversational context. "
                "Use your native OpenClaw tools, specialist agents and Narratiive control-plane plugin whenever current "
                "business state, delegated work, preparation, approval or execution evidence is required. Investigate safe "
                "questions yourself before asking Matt. Keep consequential external actions behind the native approval boundary. "
                "Treat returned evidence as authoritative and never claim that an external action happened or worked without it."
            ),
        }

        payload = self._post_openclaw(request_body)
        reply = self._extract_text(payload)
        if not reply:
            raise TonyAgentGatewayError("OpenClaw returned no conversational response")
        return reply

    def _post_openclaw(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-openclaw-agent-id": self.config.agent_id,
            "x-openclaw-session-key": self.config.session_key,
            "x-openclaw-message-channel": "telegram",
        }
        if self.config.gateway_token:
            headers["Authorization"] = f"Bearer {self.config.gateway_token}"
        payload = self._post_json(self.config.responses_url, body, headers=headers, label="OpenClaw")
        if not isinstance(payload, dict):
            raise TonyAgentGatewayError("OpenClaw returned an invalid response object")
        return payload

    def _post_json(self, url: str, body: dict[str, Any], *, headers: dict[str, str], label: str) -> Any:
        request = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise TonyAgentGatewayError(f"{label} returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TonyAgentGatewayError(f"{label} request failed: {exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TonyAgentGatewayError(f"{label} returned invalid JSON") from exc

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
