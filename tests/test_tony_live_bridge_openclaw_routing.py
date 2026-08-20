from __future__ import annotations

import io
import json
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest import mock

from openclaw.tony_agent_gateway import TonyAgentGatewayError
from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.inbound_leads import FileInboundLeadStore


class TonyLiveBridgeOpenClawRoutingTests(unittest.TestCase):
    def _request(self, app: LeadAwareTonyApplication, text: str) -> tuple[str, dict]:
        body = json.dumps({"text": text, "source": "telegram"}).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/telegram/inbound",
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(body),
        }
        captured: dict[str, object] = {}
        response = app(
            environ,
            lambda status, headers: captured.update(status=status, headers=headers),
        )
        return str(captured["status"]), json.loads(b"".join(response))

    def _app(self, tmp: str):
        base = mock.Mock()
        base.bridge_token = ""
        base._handle_telegram_command.return_value = (
            HTTPStatus.OK,
            {"ok": True, "reply": "deterministic slash response", "command": "status", "status": "ok", "data": {}},
        )
        gateway = mock.Mock()
        gateway.converse.side_effect = lambda text: f"OpenClaw heard: {text}"
        store = FileInboundLeadStore(Path(tmp) / "leads.json")
        return LeadAwareTonyApplication(base, store, agent_gateway=gateway), base, gateway

    def test_plain_language_uses_openclaw_not_legacy_command_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, base, gateway = self._app(tmp)
            status, payload = self._request(app, "Tony. What should I be working on?")

        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["reply"], "OpenClaw heard: Tony. What should I be working on?")
        self.assertEqual(payload["data"]["runtime"], "openclaw")
        gateway.converse.assert_called_once_with("Tony. What should I be working on?")
        base._handle_telegram_command.assert_not_called()

    def test_acceptance_conversation_and_typos_all_bypass_phrase_router(self):
        messages = (
            "Morning Tony, anything important?",
            "Whta shoudl I focus on today?",
            "what did they say?",
            "sort that out",
            "use Thursday",
            "send it",
            "did it go?",
            "How is the Research Agent getting on?",
            "And Strategy?",
            "What about the Creative Director?",
            "Is Production blocked?",
        )
        with tempfile.TemporaryDirectory() as tmp:
            app, base, gateway = self._app(tmp)
            for message in messages:
                with self.subTest(message=message):
                    status, payload = self._request(app, message)
                    self.assertTrue(status.startswith("200"))
                    self.assertEqual(payload["data"]["runtime"], "openclaw")

        self.assertEqual([call.args[0] for call in gateway.converse.call_args_list], list(messages))
        base._handle_telegram_command.assert_not_called()

    def test_only_explicit_slash_commands_use_deterministic_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, base, gateway = self._app(tmp)
            status, payload = self._request(app, "/status")

        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["reply"], "deterministic slash response")
        base._handle_telegram_command.assert_called_once_with("/status")
        gateway.converse.assert_not_called()

    def test_openclaw_failure_fails_closed_instead_of_falling_back_to_phrase_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, base, gateway = self._app(tmp)
            gateway.converse.side_effect = TonyAgentGatewayError("gateway unavailable")
            status, payload = self._request(app, "Tony. What should I be working on?")

        self.assertTrue(status.startswith("503"))
        self.assertEqual(payload["error"]["code"], "openclaw_conversation_unavailable")
        base._handle_telegram_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
