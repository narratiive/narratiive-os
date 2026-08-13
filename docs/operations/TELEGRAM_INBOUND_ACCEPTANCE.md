# Telegram inbound acceptance check

After deployment and LaunchAgent installation:

1. Send `What inbound leads did we get today?` to Tony in Telegram.
2. Tony must reply in the same chat without requiring a slash command.
3. The reply must be generated through the local `8790/telegram/inbound` bridge path.
4. Restarting the inbound LaunchAgent must not replay the same Telegram message.
5. Messages from chat IDs other than `TONY_TELEGRAM_CHAT_ID` must be ignored.
