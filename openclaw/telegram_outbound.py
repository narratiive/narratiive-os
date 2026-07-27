from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramDeliveryError(RuntimeError):
    """Raised when outbound Telegram delivery is misconfigured or fails."""


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    bot_token: str
    default_chat_id: str
    api_base: str = "https://api.telegram.org"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise TelegramDeliveryError("TONY_TELEGRAM_BOT_TOKEN is required")
        if not self.default_chat_id.strip():
            raise TelegramDeliveryError("TONY_TELEGRAM_CHAT_ID is required")
        if not self.api_base.lower().startswith("https://"):
            raise TelegramDeliveryError("Telegram API base must use HTTPS")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TelegramConfig":
        bot_token = str(env.get("TONY_TELEGRAM_BOT_TOKEN", "")).strip()
        chat_id = str(env.get("TONY_TELEGRAM_CHAT_ID", "")).strip()
        if not bot_token or not chat_id:
            raise TelegramDeliveryError(
                "TONY_TELEGRAM_BOT_TOKEN and TONY_TELEGRAM_CHAT_ID are required for "
                "outbound proactive delivery"
            )
        api_base = str(env.get("TONY_TELEGRAM_API_BASE", "")).strip() or "https://api.telegram.org"
        timeout_raw = str(env.get("TONY_TELEGRAM_TIMEOUT_SECONDS", "")).strip() or "10"
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise TelegramDeliveryError(
                f"TONY_TELEGRAM_TIMEOUT_SECONDS must be numeric: {timeout_raw}"
            ) from exc
        return cls(
            bot_token=bot_token,
            default_chat_id=chat_id,
            api_base=api_base,
            timeout_seconds=timeout_seconds,
        )


class TelegramSender:
    """Outbound Telegram Bot API adapter for Tony's proactive delivery coordinator.

    This is deliberately narrow: it sends one message to one chat and raises
    ``TelegramDeliveryError`` on any failure so the caller's bounded-retry loop
    can treat every failure mode identically. It never logs or persists the bot
    token.
    """

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config

    def send(self, chat_id: str, text: str) -> None:
        if not chat_id.strip():
            raise TelegramDeliveryError("chat_id is required")
        if not text.strip():
            raise TelegramDeliveryError("text is required")

        url = f"{self.config.api_base.rstrip('/')}/bot{self.config.bot_token}/sendMessage"
        body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise TelegramDeliveryError(f"Telegram API returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TelegramDeliveryError(f"Telegram API request failed: {exc}") from exc

        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TelegramDeliveryError("Telegram API returned an invalid response") from exc
        if not isinstance(payload, dict) or not payload.get("ok"):
            raise TelegramDeliveryError(f"Telegram API rejected the message: {payload}")
