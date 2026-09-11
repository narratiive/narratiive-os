# Tony Telegram inbound

Tony's Telegram conversation is owned by the published n8n Telegram Trigger in
`Narratiive Ops - Status Lookup - Formatted v2` (`s7TvzzAsJRKLRDU7`). OpenClaw's
native Telegram channel and the retired standalone `getUpdates` poller must both
remain disabled so only one component owns bot updates.

```text
Telegram webhook
  -> stable HTTPS ngrok endpoint
  -> n8n Telegram Trigger
  -> authenticated HTTP Request: POST http://127.0.0.1:8790/telegram/inbound
  -> Tony bridge
  -> ordinary conversation: OpenClaw agent `tony` and synchronous bridge response
  -> substantive work: durable correlated work item and immediate acknowledgement
  -> n8n formatter
  -> Telegram Send node
  -> acknowledgement in the originating chat
  -> durable Tony worker -> OpenClaw/specialists -> proactive result in the same chat
```

The Telegram credential remains in n8n. `TONY_BRIDGE_TOKEN` remains only in the
mode-`0600` runtime environment file. The HTTP Request node must send this JSON
header expression under n8n 2.20:

```text
={{ JSON.stringify({ Authorization: 'Bearer ' + $env.TONY_BRIDGE_TOKEN }) }}
```

The active workflow version must be published after changing a node. An edited
draft is not the version n8n activates after restart.

The HTTP Request body must include `text`, `chat_id`, `message_id`, and
`update_id`. The latter three fields give durable work a stable Telegram
correlation and make an n8n replay resolve to the existing work item rather than
commissioning duplicate model work. Substantive work is persisted beneath
`TONY_CONVERSATION_WORK_ROOT` (default `.runtime/conversation-work`), with
atomic current-state snapshots and an append-only `events.jsonl`. The
`com.narratiive.tony-conversation-worker` LaunchAgent recovers expired work
leases, keeps model execution outside the inbound HTTP lifetime, and retries
generation and Telegram delivery independently. Ordinary conversation remains
synchronous. This does not grant any external-action authority: consequential
actions continue through the existing approval-gated command boundary.

When Tony delegates and calls OpenClaw's `sessions_yield`, the initial OpenClaw
HTTP response is not a completed work result. The worker keeps the durable run
open and observes the correlated Tony session until the pushed specialist
completion has been reviewed and Tony produces a normal final turn. On restart,
an already-resumed final turn is recovered from that same session before any new
model request is made, preventing duplicate specialist execution.

## Durable macOS startup

Install the n8n and ngrok LaunchAgents with the canonical repository Python.
Use the stable HTTPS n8n base URL, not the workflow-specific webhook path:

```bash
cd ~/Documents/narratiive-os
.venv/bin/python scripts/install_n8n_telegram_ingress.py \
  --python .venv/bin/python \
  --env-file "$HOME/.config/narratiive/runtime.env" \
  --node "$HOME/.nvm/versions/node/v25.9.0/bin/node" \
  --n8n "$HOME/.nvm/versions/node/v25.9.0/bin/n8n" \
  --ngrok /opt/homebrew/bin/ngrok \
  --webhook-url https://lushly-spoof-reheat.ngrok-free.dev/
```

The installer creates `com.narratiive.n8n-tunnel` and
`com.narratiive.n8n`, both with `RunAtLoad` and `KeepAlive`. It pins:

- `WEBHOOK_URL` to the HTTPS public n8n base URL so Telegram accepts activation;
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` so the bridge header can read the runtime
  token without copying it into n8n or a plist; and
- the selected Node binary directory in `PATH` so n8n's task broker can start
  JavaScript workers under launchd; and
- the stable ngrok hostname, so a restart does not change webhook ownership.

It refuses installation when OpenClaw native Telegram is enabled, validates the
secure environment file, and removes the retired
`com.narratiive.telegram-inbound` LaunchAgent. No credential value is written to
the LaunchAgent files or command output. The audited `run_with_env.py` loader is
copied to `~/Library/Application Support/Narratiive/` so launchd does not depend
on interactive access to the repository under macOS's protected Documents
folder.

## Verification

```bash
launchctl print "gui/$(id -u)/com.narratiive.n8n-tunnel"
launchctl print "gui/$(id -u)/com.narratiive.n8n"
curl -fsS http://127.0.0.1:5678/healthz
curl -fsS http://127.0.0.1:8790/health
```

Inspect n8n startup logs for successful activation of workflow
`s7TvzzAsJRKLRDU7`, and inspect Telegram `getWebhookInfo` through a secret-safe
credential check. Its URL must be the stable HTTPS host plus n8n's production
webhook path, with no webhook error and no unexplained pending updates.

Then complete the live acceptance in `TELEGRAM_INBOUND_ACCEPTANCE.md`. A green
unit test alone is not evidence that Telegram delivered a message.
