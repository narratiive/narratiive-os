from __future__ import annotations

import io
import json
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path

from openclaw.telegram_inbound import TelegramInboundConfig, TelegramInboundService
from openclaw.tony_live_bridge import LeadAwareTonyApplication


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


class FakeBase:
    bridge_token = "secret"

    def _handle_telegram_command(self, text: str):
        return HTTPStatus.OK, {"ok": True, "reply": f"answered:{text}", "message": f"answered:{text}"}

    def __call__(self, environ, start_response):
        raise AssertionError("base should not be called for /telegram/inbound")


class FakeAgentGateway:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def converse(self, text: str) -> str:
        self.messages.append(text)
        return f"answered:{text}"


class FakeWorkflowCommands:
    def supports(self, text):
        return text.startswith("/workflow")

    def execute(self, text, objects, *, principal_id=""):
        return type(
            "Response",
            (),
            {
                "status": "healthy",
                "message": f"principal:{principal_id}",
                "to_dict": lambda self: {
                    "command": "workflow",
                    "status": "healthy",
                    "message": self.message,
                    "data": {},
                },
            },
        )()


class DummyLeadStore:
    def upsert(self, lead):
        raise AssertionError("lead store should not be called")


class TelegramInboundTests(unittest.TestCase):
    def test_config_uses_conversational_bridge_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = TelegramInboundConfig.from_env(
                {
                    "TONY_TELEGRAM_BOT_TOKEN": "token",
                    "TONY_TELEGRAM_CHAT_ID": "123",
                    "TONY_BRIDGE_TOKEN": "secret",
                },
                repository_root=Path(tmp),
            )
        self.assertEqual(config.bridge_url, "http://127.0.0.1:8790/telegram/inbound")

    def test_config_upgrades_legacy_root_bridge_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = TelegramInboundConfig.from_env(
                {
                    "TONY_TELEGRAM_BOT_TOKEN": "token",
                    "TONY_TELEGRAM_CHAT_ID": "123",
                    "TONY_TELEGRAM_BRIDGE_URL": "http://127.0.0.1:8790",
                },
                repository_root=Path(tmp),
            )
        self.assertEqual(config.bridge_url, "http://127.0.0.1:8790/telegram/inbound")

    def test_process_update_replies_only_to_allowed_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = TelegramInboundConfig(
                bot_token="token",
                allowed_chat_id="123",
                offset_path=Path(tmp) / "offset.json",
            )
            service = TelegramInboundService(config)
            sender = FakeSender()
            service.sender = sender
            service._execute_tony = lambda text: f"Tony:{text}"  # type: ignore[method-assign]
            service._process_update({"message": {"chat": {"id": 123}, "text": "What inbound leads did we get today?"}})
            service._process_update({"message": {"chat": {"id": 999}, "text": "ignore me"}})
        self.assertEqual(sender.messages, [("123", "Tony:What inbound leads did we get today?")])

    def test_user_reply_sanitizer_removes_internal_error_codes(self):
        reply = "I couldn't phrase that safely.\nError: terminology_violation\nerror_code: hidden"
        self.assertEqual(
            TelegramInboundService._sanitize_user_reply(reply),
            "I couldn't phrase that safely.",
        )

    def test_slash_command_passes_authenticated_chat_as_principal(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = TelegramInboundService(
                TelegramInboundConfig(
                    bot_token="token",
                    allowed_chat_id="123",
                    bridge_token="bridge-secret",
                    offset_path=Path(tmp) / "offset.json",
                )
            )
            captured = {}

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def read(self):
                    return b'{"reply":"ok"}'

            def fake_urlopen(request, timeout):
                captured["body"] = json.loads(request.data.decode("utf-8"))
                captured["authorization"] = request.headers.get("Authorization")
                return Response()

            from unittest.mock import patch

            with patch("openclaw.telegram_inbound.urlopen", fake_urlopen):
                self.assertEqual(service._execute_legacy_command("/approve run because reviewed"), "ok")

        self.assertEqual(captured["body"]["principal_id"], "telegram:123")
        self.assertEqual(captured["authorization"], "Bearer bridge-secret")

    def test_offsets_persist_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "offset.json"
            service = TelegramInboundService(
                TelegramInboundConfig(bot_token="token", allowed_chat_id="123", offset_path=path)
            )
            service._write_offset(42)
            self.assertEqual(service._read_offset(), 42)

    def test_live_bridge_accepts_plain_telegram_text(self):
        gateway = FakeAgentGateway()
        base = FakeBase()
        app = LeadAwareTonyApplication(base, DummyLeadStore(), agent_gateway=gateway)
        body = json.dumps({"text": "What inbound leads did we get today?"}).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/telegram/inbound",
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json",
            "HTTP_AUTHORIZATION": "Bearer secret",
            "wsgi.input": io.BytesIO(body),
        }
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        response = b"".join(app(environ, start_response))
        payload = json.loads(response.decode("utf-8"))
        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(payload["reply"], "answered:What inbound leads did we get today?")
        self.assertEqual(payload["data"]["runtime"], "openclaw")
        self.assertEqual(gateway.messages, ["What inbound leads did we get today?"])

    def test_live_bridge_only_trusts_configured_workflow_principal(self):
        app = LeadAwareTonyApplication(
            FakeBase(),
            DummyLeadStore(),
            agent_gateway=FakeAgentGateway(),
            workflow_command_service=FakeWorkflowCommands(),
            authorised_principal_id="telegram:123",
        )

        def call(principal):
            body = json.dumps({"text": "/workflow safe", "principal_id": principal}).encode("utf-8")
            environ = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/telegram/inbound",
                "CONTENT_LENGTH": str(len(body)),
                "HTTP_AUTHORIZATION": "Bearer secret",
                "wsgi.input": io.BytesIO(body),
            }
            response = b"".join(app(environ, lambda status, headers: None))
            return json.loads(response.decode("utf-8"))

        self.assertEqual(call("telegram:123")["reply"], "principal:telegram:123")
        self.assertEqual(call("telegram:999")["reply"], "principal:")


if __name__ == "__main__":
    unittest.main()
