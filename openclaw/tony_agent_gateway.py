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
    control_plane_url: str = "http://127.0.0.1:8790/telegram/inbound"
    control_plane_token: str = ""
    timeout_seconds: float = 120.0
    max_tool_rounds: int = 4

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TonyAgentGatewayConfig":
        base = str(env.get("OPENCLAW_GATEWAY_URL", "")).strip().rstrip("/") or "http://127.0.0.1:18789"
        responses_url = str(env.get("TONY_OPENCLAW_RESPONSES_URL", "")).strip() or f"{base}/v1/responses"
        control_plane_url = str(env.get("TONY_AGENT_CONTROL_PLANE_URL", "")).strip()
        if not control_plane_url:
            control_plane_url = str(env.get("TONY_TELEGRAM_BRIDGE_URL", "")).strip() or "http://127.0.0.1:8790/telegram/inbound"
        control_plane_url = control_plane_url.rstrip("/")
        if control_plane_url in {"http://127.0.0.1:8790", "http://localhost:8790"}:
            control_plane_url += "/telegram/inbound"
        return cls(
            responses_url=responses_url,
            agent_id=str(env.get("TONY_OPENCLAW_AGENT_ID", "")).strip() or "tony",
            gateway_token=str(env.get("OPENCLAW_GATEWAY_TOKEN", "")).strip(),
            session_key=str(env.get("TONY_OPENCLAW_SESSION_KEY", "")).strip() or "narratiive:tony:telegram",
            control_plane_url=control_plane_url,
            control_plane_token=str(env.get("TONY_BRIDGE_TOKEN", "")).strip(),
            timeout_seconds=float(env.get("TONY_OPENCLAW_TIMEOUT_SECONDS", "120")),
            max_tool_rounds=max(1, int(env.get("TONY_OPENCLAW_MAX_TOOL_ROUNDS", "4"))),
        )


class TonyAgentGateway:
    """Natural-language ingress for Tony 2.0 with bounded Narratiive tools.

    OpenClaw owns semantic interpretation and conversation continuity. Narratiive OS
    remains the source of truth for live business state. The agent receives a deliberately
    small read-only tool surface and never gets to turn arbitrary model text into a
    deterministic command.
    """

    _TOOLS = (
        {
            "type": "function",
            "name": "get_executive_brief",
            "description": (
                "Read Tony's current evidence-backed Narratiive executive brief. Use this when Matt asks "
                "what matters, what needs attention, what to focus on, or for a morning/evening business overview."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["morning", "evening"],
                        "description": "Which executive brief to read. Default to morning for current priorities.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_current_leads",
            "description": (
                "Read the authoritative current Narratiive inbound lead/pipeline view. Use this before making claims "
                "about active leads, opportunities, contacts or the commercial pipeline."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "get_open_work_status",
            "description": (
                "Read the current evidence-backed status of Tony's open or most recently completed executive action. "
                "Use this for questions about what is waiting, blocked, stalled, delegated, completed, or currently in progress."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "get_recent_execution_status",
            "description": (
                "Check verified evidence for the most recent consequential action. Use this when Matt asks whether "
                "something actually sent, happened, completed, or worked. Execution proof and business outcome proof are separate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["execution", "outcome"],
                        "description": "Use execution to verify that the action happened; outcome to assess whether it worked.",
                    }
                },
                "additionalProperties": False,
            },
        },
    )

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

        request_body: dict[str, Any] = {
            "model": f"openclaw/{self.config.agent_id}",
            "input": message,
            "instructions": (
                "You are Tony, Narratiive's Chief of Staff. Converse naturally. When a question depends on current "
                "Narratiive state, use the supplied read tools instead of guessing. Use open-work status for live delegated "
                "or stalled work, and recent-execution status before claiming that an external action happened or worked. "
                "Treat tool output as evidence, separate verified facts from judgement, and never claim an external action "
                "happened without returned evidence."
            ),
            "tools": list(self._TOOLS),
            "tool_choice": "auto",
        }

        for _ in range(self.config.max_tool_rounds):
            payload = self._post_openclaw(request_body)
            calls = self._extract_tool_calls(payload)
            if not calls:
                reply = self._extract_text(payload)
                if not reply:
                    raise TonyAgentGatewayError("OpenClaw returned no conversational response")
                return reply

            response_id = str(payload.get("id") or "").strip() if isinstance(payload, dict) else ""
            if not response_id:
                raise TonyAgentGatewayError("OpenClaw tool call response did not include a response id")

            outputs = []
            for call in calls:
                result = self._execute_tool(call["name"], call["arguments"])
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(result, sort_keys=True),
                    }
                )
            request_body = {
                "model": f"openclaw/{self.config.agent_id}",
                "input": outputs,
                "previous_response_id": response_id,
                "tools": list(self._TOOLS),
                "tool_choice": "auto",
            }

        raise TonyAgentGatewayError("OpenClaw exceeded the bounded tool-call limit")

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

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_executive_brief":
            period = str(arguments.get("period") or "morning").strip().casefold()
            if period not in {"morning", "evening"}:
                return {"ok": False, "error": "period must be morning or evening"}
            command = f"/{period}"
        elif name == "get_current_leads":
            command = "/leads"
        elif name == "get_open_work_status":
            # Compatibility read against the existing deterministic status layer. The user's wording
            # is interpreted by OpenClaw; this fixed canonical query is never derived by phrase matching.
            command = "what's the status"
        elif name == "get_recent_execution_status":
            scope = str(arguments.get("scope") or "execution").strip().casefold()
            if scope not in {"execution", "outcome"}:
                return {"ok": False, "error": "scope must be execution or outcome"}
            command = "did that happen" if scope == "execution" else "did that work"
        else:
            return {"ok": False, "error": f"unsupported tool: {name}"}

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.control_plane_token:
            headers["Authorization"] = f"Bearer {self.config.control_plane_token}"
        try:
            payload = self._post_json(
                self.config.control_plane_url,
                {"text": command, "source": "openclaw_agent_tool"},
                headers=headers,
                label="Narratiive control plane",
            )
        except TonyAgentGatewayError as exc:
            return {"ok": False, "error": str(exc)}
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Narratiive control plane returned invalid data"}
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
    def _extract_tool_calls(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("output"), list):
            return []
        calls: list[dict[str, Any]] = []
        for item in payload["output"]:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            name = str(item.get("name") or "").strip()
            call_id = str(item.get("call_id") or "").strip()
            raw_arguments = item.get("arguments")
            if isinstance(raw_arguments, str):
                try:
                    arguments = json.loads(raw_arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
            elif isinstance(raw_arguments, dict):
                arguments = dict(raw_arguments)
            else:
                arguments = {}
            if name and call_id:
                calls.append({"name": name, "call_id": call_id, "arguments": arguments})
        return calls

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