from __future__ import annotations

import json
from io import BytesIO

import pytest

from openclaw.tony_agent_gateway import TonyAgentGateway, TonyAgentGatewayConfig, TonyAgentGatewayError


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self): return self._raw


def test_only_explicit_slash_commands_use_deterministic_surface():
    assert TonyAgentGateway.is_system_command("/health") is True
    assert TonyAgentGateway.is_system_command("  /diagnostics") is True
    assert TonyAgentGateway.is_system_command("Morning Tony, anything important?") is False
    assert TonyAgentGateway.is_system_command("whta shoudl I focus on today?") is False
    assert TonyAgentGateway.is_system_command("sort that out") is False
    assert TonyAgentGateway.is_system_command("how is the research agent getting on?") is False


def test_gateway_preserves_session_and_agent_routing(monkeypatch):
    captured = {}
    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return _Response({"output_text": "Jimmy replied. I'd handle that first."})
    monkeypatch.setattr("openclaw.tony_agent_gateway.urlopen", fake_urlopen)
    gateway = TonyAgentGateway(TonyAgentGatewayConfig(agent_id="tony", session_key="narratiive:tony:telegram", gateway_token="secret"))
    assert gateway.converse("What did they say?") == "Jimmy replied. I'd handle that first."
    assert captured["body"] == {"model": "openclaw/tony", "input": "What did they say?"}
    headers = {key.casefold(): value for key, value in captured["headers"].items()}
    assert headers["x-openclaw-agent-id"] == "tony"
    assert headers["x-openclaw-session-key"] == "narratiive:tony:telegram"
    assert headers["authorization"] == "Bearer secret"


@pytest.mark.parametrize("text", [
    "Morning Tony, anything important?",
    "whta shoudl I focus on today?",
    "What did they say?",
    "sort that out",
    "use Thursday",
    "send it",
    "did it go?",
    "how is the strategy agent?",
    "how is the creative director getting on?",
    "what is production working on?",
])
def test_acceptance_language_never_requires_phrase_matching(text):
    assert TonyAgentGateway.is_system_command(text) is False


def test_slash_command_cannot_be_sent_to_agent_gateway():
    gateway = TonyAgentGateway(TonyAgentGatewayConfig())
    with pytest.raises(TonyAgentGatewayError, match="slash commands"):
        gateway.converse("/health")
