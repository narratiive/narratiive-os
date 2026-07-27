from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from openclaw.telegram_outbound import TelegramConfig, TelegramDeliveryError, TelegramSender


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> None:
        return None


class TelegramConfigTests(unittest.TestCase):
    def test_from_env_requires_bot_token_and_chat_id(self):
        with self.assertRaises(TelegramDeliveryError):
            TelegramConfig.from_env({})
        with self.assertRaises(TelegramDeliveryError):
            TelegramConfig.from_env({"TONY_TELEGRAM_BOT_TOKEN": "token"})

    def test_from_env_builds_config_with_defaults(self):
        config = TelegramConfig.from_env(
            {"TONY_TELEGRAM_BOT_TOKEN": "token", "TONY_TELEGRAM_CHAT_ID": "123"}
        )
        self.assertEqual(config.bot_token, "token")
        self.assertEqual(config.default_chat_id, "123")
        self.assertEqual(config.api_base, "https://api.telegram.org")
        self.assertEqual(config.timeout_seconds, 10.0)

    def test_from_env_rejects_non_numeric_timeout(self):
        with self.assertRaisesRegex(TelegramDeliveryError, "numeric"):
            TelegramConfig.from_env(
                {
                    "TONY_TELEGRAM_BOT_TOKEN": "token",
                    "TONY_TELEGRAM_CHAT_ID": "123",
                    "TONY_TELEGRAM_TIMEOUT_SECONDS": "soon",
                }
            )

    def test_rejects_non_https_api_base(self):
        with self.assertRaisesRegex(TelegramDeliveryError, "HTTPS"):
            TelegramConfig(bot_token="t", default_chat_id="1", api_base="http://example.com")

    def test_rejects_missing_bot_token_or_chat_id(self):
        with self.assertRaises(TelegramDeliveryError):
            TelegramConfig(bot_token=" ", default_chat_id="1")
        with self.assertRaises(TelegramDeliveryError):
            TelegramConfig(bot_token="t", default_chat_id=" ")


class TelegramSenderTests(unittest.TestCase):
    def sender(self) -> TelegramSender:
        return TelegramSender(
            TelegramConfig(bot_token="test-token", default_chat_id="12345")
        )

    def test_sends_message_to_the_configured_bot_endpoint(self):
        sender = self.sender()
        with patch("openclaw.telegram_outbound.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _FakeResponse({"ok": True})
            sender.send("12345", "Morning brief — healthy")

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://api.telegram.org/bottest-token/sendMessage"
        )
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {"chat_id": "12345", "text": "Morning brief — healthy"})

    def test_raises_on_http_error(self):
        sender = self.sender()
        with patch("openclaw.telegram_outbound.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                "url", 500, "Internal Server Error", {}, io.BytesIO(b"boom")
            )
            with self.assertRaises(TelegramDeliveryError):
                sender.send("12345", "hello")

    def test_raises_on_network_error(self):
        sender = self.sender()
        with patch("openclaw.telegram_outbound.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError("connection refused")
            with self.assertRaises(TelegramDeliveryError):
                sender.send("12345", "hello")

    def test_raises_when_telegram_reports_not_ok(self):
        sender = self.sender()
        with patch("openclaw.telegram_outbound.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _FakeResponse({"ok": False, "description": "bad"})
            with self.assertRaises(TelegramDeliveryError):
                sender.send("12345", "hello")

    def test_raises_on_invalid_json_response(self):
        class _BadResponse(_FakeResponse):
            def read(self) -> bytes:
                return b"not json"

        sender = self.sender()
        with patch("openclaw.telegram_outbound.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _BadResponse({})
            with self.assertRaises(TelegramDeliveryError):
                sender.send("12345", "hello")

    def test_requires_non_empty_chat_id_and_text(self):
        sender = self.sender()
        with self.assertRaisesRegex(TelegramDeliveryError, "chat_id"):
            sender.send(" ", "hello")
        with self.assertRaisesRegex(TelegramDeliveryError, "text"):
            sender.send("12345", " ")


if __name__ == "__main__":
    unittest.main()
