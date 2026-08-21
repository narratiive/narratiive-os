# Tony Telegram inbound

Tony's Telegram conversation is owned directly by OpenClaw. Narratiive OS no longer runs a second `getUpdates` poller for the same bot token.

Flow:

```text
Telegram
  -> OpenClaw native Telegram channel
  -> managed default Telegram binding -> agent `tony`
  -> Tony workspace + durable OpenClaw session
  -> OpenClaw specialist/session tools as needed
  -> Narratiive control-plane plugin for business state, approvals and evidence
  -> Telegram reply from OpenClaw
```

This is deliberate. Telegram permits only one long-poll consumer per bot token, and OpenClaw's Telegram runtime already provides long polling, per-chat sequencing, durable channel/session context and direct routing into an agent workspace. Keeping Narratiive's historical `com.narratiive.telegram-inbound` LaunchAgent alive beside OpenClaw can create `getUpdates` conflicts and silent or lost turns.

## Activation

Apply the managed OpenClaw fleet:

```bash
cd ~/Documents/narratiive-os
.venv/bin/python scripts/install_openclaw_fleet.py --apply
openclaw gateway restart
```

The fleet installer:

- preserves the existing Telegram channel/account configuration;
- adds the default Telegram route binding to agent `tony` while preserving more-specific Telegram bindings;
- installs Tony and the five specialist workspaces;
- enables the Narratiive control-plane plugin; and
- on macOS, retires and removes the legacy `com.narratiive.telegram-inbound` LaunchAgent only when the native OpenClaw Telegram channel is enabled.

The old `scripts/install_telegram_inbound_agent.py` entrypoint is intentionally deprecated and cannot reinstall a second poller.

## Verification

After restarting the Gateway, verify both the route and the channel before testing Tony conversationally:

```bash
openclaw agents list --bindings
openclaw channels status --probe
```

The default Telegram account should route to `tony`, and Telegram should report healthy polling without a persistent `getUpdates` 409 conflict.

Then test normal language in Telegram, for example:

- `Morning Tony, anything important?`
- `Tony - what should I be working on today?`
- typo variants and contextual follow-ups such as `what did they say?`, `sort that out`, `use Thursday`, `send it`, and `did it go?`

Only explicit `/slash` commands belong to Narratiive OS's deterministic command surface. Ordinary language must stay inside OpenClaw's conversational runtime.
