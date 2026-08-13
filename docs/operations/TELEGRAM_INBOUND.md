# Tony Telegram inbound

Narratiive OS receives Matt's Telegram messages through a local long-polling service.

Flow:

```text
Telegram Bot API getUpdates
  -> openclaw.telegram_inbound
  -> http://127.0.0.1:8790/telegram/inbound
  -> Tony executive command service
  -> Telegram Bot API sendMessage
```

The service intentionally uses long polling rather than a public webhook so the Mac runtime does not need another internet-facing route. Only `TONY_TELEGRAM_CHAT_ID` is accepted. Update offsets are persisted at `.runtime/telegram-inbound-offset.json` so restarts do not replay previously handled messages.

Required runtime environment variables already used by outbound delivery:

- `TONY_TELEGRAM_BOT_TOKEN`
- `TONY_TELEGRAM_CHAT_ID`
- `TONY_BRIDGE_TOKEN` when the local Tony bridge is authenticated

Install or refresh the LaunchAgent once with:

```bash
cd ~/Documents/narratiive-os
.venv/bin/python scripts/install_telegram_inbound_agent.py
```

After installation, `com.narratiive.telegram-inbound` runs continuously with `KeepAlive` and restarts automatically if it exits.
