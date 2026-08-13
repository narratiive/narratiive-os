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

    def test_offsets_persist_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "offset.json"
            service = TelegramInboundService(
                TelegramInboundConfig(bot_token="token", allowed_chat_id="123", offset_path=path)
            )
            service._write_offset(42)
            self.assertEqual(service._read_offset(), 42)

    def test_live_bridge_accepts_plain_telegram_text(self):
        app = LeadAwareTonyApplication(FakeBase(), DummyLeadStore())
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


if __name__ == "__main__":
    unittest.main()
