from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from openclaw.telegram_outbound import TelegramConfig, TelegramDeliveryError, TelegramSender
from openclaw.tony_agent_gateway import TonyAgentGateway, TonyAgentGatewayConfig, TonyAgentGatewayError


class TelegramInboundError(RuntimeError):
    """Raised when inbound Telegram polling or dispatch fails."""


@dataclass(frozen=True, slots=True)
class TelegramInboundConfig:
    bot_token: str
    allowed_chat_id: str
    bridge_url: str = "http://127.0.0.1:8790/telegram/inbound"
    bridge_token: str = ""
    api_base: str = "https://api.telegram.org"
    poll_timeout_seconds: int = 25
    request_timeout_seconds: float = 35.0
    offset_path: Path = Path(".runtime/telegram-inbound-offset.json")

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, repository_root: Path) -> "TelegramInboundConfig":
        bot_token = str(env.get("TONY_TELEGRAM_BOT_TOKEN", "")).strip()
        chat_id = str(env.get("TONY_TELEGRAM_CHAT_ID", "")).strip()
        if not bot_token or not chat_id:
            raise TelegramInboundError("TONY_TELEGRAM_BOT_TOKEN and TONY_TELEGRAM_CHAT_ID are required for inbound Telegram")
        bridge_url = str(env.get("TONY_TELEGRAM_BRIDGE_URL", "")).strip() or "http://127.0.0.1:8790/telegram/inbound"
        bridge_url = bridge_url.rstrip("/")
        if bridge_url in {"http://127.0.0.1:8790", "http://localhost:8790"}:
            bridge_url += "/telegram/inbound"
        offset_raw = str(env.get("TONY_TELEGRAM_OFFSET_PATH", "")).strip()
        offset_path = Path(offset_raw).expanduser() if offset_raw else repository_root / ".runtime" / "telegram-inbound-offset.json"
        return cls(
            bot_token=bot_token,
            allowed_chat_id=chat_id,
            bridge_url=bridge_url,
            bridge_token=str(env.get("TONY_BRIDGE_TOKEN", "")).strip(),
            api_base=(str(env.get("TONY_TELEGRAM_API_BASE", "")).strip() or "https://api.telegram.org").rstrip("/"),
            offset_path=offset_path.resolve(),
        )


class TelegramInboundService:
    """Receive Telegram messages and preserve one human conversational surface.

    Ordinary language goes to OpenClaw's agent runtime, which owns semantic
    interpretation and durable conversation context. Only explicit slash
    commands use Narratiive OS's legacy deterministic command surface.
    """

    def __init__(self, config: TelegramInboundConfig, *, agent_gateway: TonyAgentGateway | None = None) -> None:
        self.config = config
        self.agent_gateway = agent_gateway or TonyAgentGateway(TonyAgentGatewayConfig.from_env(os.environ))
        self.sender = TelegramSender(TelegramConfig(bot_token=config.bot_token, default_chat_id=config.allowed_chat_id, api_base=config.api_base, timeout_seconds=10.0))

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except (TelegramInboundError, TelegramDeliveryError):
                time.sleep(2.0)

    def run_once(self) -> int:
        offset = self._read_offset()
        updates = self._fetch_updates(offset)
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id", -1))
            if update_id < 0:
                continue
            try:
                self._process_update(update)
                processed += 1
            finally:
                self._write_offset(update_id + 1)
        return processed

    def _fetch_updates(self, offset: int) -> list[dict[str, Any]]:
        query = urlencode({"offset": offset, "timeout": self.config.poll_timeout_seconds, "allowed_updates": json.dumps(["message"])})
        request = Request(f"{self.config.api_base}/bot{self.config.bot_token}/getUpdates?{query}", headers={"Accept": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise TelegramInboundError(f"Telegram getUpdates returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TelegramInboundError(f"Telegram getUpdates failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TelegramInboundError("Telegram getUpdates returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise TelegramInboundError(f"Telegram getUpdates rejected: {payload}")
        result = payload.get("result", [])
        return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    def _process_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        if not isinstance(chat, dict) or str(chat.get("id", "")).strip() != self.config.allowed_chat_id:
            return
        text = str(message.get("text", "")).strip()
        if not text:
            return
        reply = self._execute_tony(text)
        self.sender.send(self.config.allowed_chat_id, reply)

    def _execute_tony(self, text: str) -> str:
        if not TonyAgentGateway.is_system_command(text):
            try:
                return self._sanitize_user_reply(self.agent_gateway.converse(text))[:3500]
            except TonyAgentGatewayError as exc:
                raise TelegramInboundError(str(exc)) from exc
        return self._execute_legacy_command(text)

    def _execute_legacy_command(self, text: str) -> str:
        body = json.dumps(
            {
                "text": text,
                "source": "telegram",
                "principal_id": f"telegram:{self.config.allowed_chat_id}",
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.bridge_token:
            headers["Authorization"] = f"Bearer {self.config.bridge_token}"
        request = Request(self.config.bridge_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=20.0) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise TelegramInboundError(f"Tony bridge returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TelegramInboundError(f"Tony bridge request failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TelegramInboundError("Tony bridge returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TelegramInboundError("Tony bridge returned an invalid response")
        reply = str(payload.get("reply") or payload.get("message") or "").strip()
        if not reply:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            reply = str(error.get("message") or "Tony couldn't complete that request reliably.").strip()
        return self._sanitize_user_reply(reply)[:3500]

    @staticmethod
    def _sanitize_user_reply(reply: str) -> str:
        lines = []
        for line in reply.splitlines():
            lowered = line.strip().casefold()
            if lowered.startswith("error:") or lowered.startswith("error_code:"):
                continue
            lines.append(line)
        cleaned = "\n".join(lines).strip()
        return cleaned or "Tony couldn't complete that request reliably."

    def _read_offset(self) -> int:
        if not self.config.offset_path.exists():
            return 0
        try:
            value = json.loads(self.config.offset_path.read_text(encoding="utf-8"))
            return max(0, int(value.get("offset", 0))) if isinstance(value, dict) else 0
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0

    def _write_offset(self, offset: int) -> None:
        self.config.offset_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config.offset_path.with_suffix(self.config.offset_path.suffix + ".tmp")
        temporary.write_text(json.dumps({"offset": int(offset)}, sort_keys=True), encoding="utf-8")
        temporary.replace(self.config.offset_path)


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    config = TelegramInboundConfig.from_env(os.environ, repository_root=repository_root)
    TelegramInboundService(config).run_forever()


if __name__ == "__main__":
    main()
