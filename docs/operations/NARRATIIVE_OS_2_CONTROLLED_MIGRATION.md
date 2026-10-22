# Narratiive OS 2.0 controlled migration

## Preserved architecture

- Telegram remains the founder interface. The active ingress is the existing n8n-to-Tony HTTP bridge; OpenClaw's native Telegram polling stays disabled to prevent duplicate updates.
- The Tony bridge continues to separate deterministic commands and consequential control-plane actions from natural-language OpenClaw conversation.
- OpenClaw remains the conversational orchestrator. Tony, Research and Strategy use the explicitly configured hosted reasoning model. Creative Director, Production and Operations inherit the local Ollama model.
- The existing file-backed workflow runtime remains the operational source of truth. It already provides run and artefact identifiers, ownership, durable status, evidence, retries, next actions and exact-version approvals.
- Notion, Google Drive, GitHub and Gmail retain their existing credential and adapter boundaries. n8n remains the automation host. No service or database was duplicated.
- The separate FIELDWORK production experiment is outside this migration and was not changed.

## Model policy

The installed OpenClaw release supports `anthropic/claude-sonnet-4-6`, which is used strictly for Tony and the reasoning-heavy Research and Strategy roles. Consequential agents have no weaker fallback configured. `ollama/qwen3.5:latest` remains the default for lower-risk production and operations work and is also the utility model for short internal title-generation tasks.

OpenClaw tool-loop detection is enabled with ordered warning, critical and global circuit-breaker thresholds. Heartbeats retain their separate 120-second bound. Existing workflow retries remain bounded by their registered retry policies.

## Usage accounting and limits

`runtime/model_usage_budget.py` reads only token metadata from OpenClaw session logs and combines it with an append-only, mode-600 ledger for direct Anthropic workflow calls. It does not read or report prompts, responses, tool payloads or credentials.

Configuration is stored in the existing mode-600 Narratiive runtime environment:

- `TONY_HOSTED_MODEL_WARNING_USD`
- `TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD`
- `TONY_HOSTED_MODEL_REQUEST_RESERVE_USD`
- optional per-million-token pricing overrides

The local guard uses a mode-600, atomic cross-process reservation ledger and blocks new Telegram-to-OpenClaw reasoning and direct Anthropic preparation when committed usage plus live request reservations reaches the hard limit. Direct preparation reserves conservative prompt/cache and maximum-output cost before dispatch. It does not silently route consequential reasoning to Ollama.

Tony's scheduled heartbeat is explicitly pinned to `ollama/qwen3.5:latest`, uses an isolated lightweight context, and therefore does not create unguarded hosted-model usage. Reset transcript archives are retained for 62 days so a complete calendar month's usage remains available to the guard even across session resets. Missing, unreadable, or malformed OpenClaw usage metadata fails closed. OpenClaw operator diagnostics and direct Gateway/API calls made outside the Tony bridge remain outside the local admission guard; they are manual engineering surfaces, not scheduled production paths, and their completed Anthropic usage is still included in accounting. The Anthropic workspace limit remains the authoritative provider-side ceiling for any such direct provider call.

Run the local status check through the existing secured environment loader:

```sh
.venv/bin/python scripts/run_with_env.py ~/.config/narratiive/runtime.env .venv/bin/python scripts/model_usage_status.py
```

Exit status is `0` below the warning threshold, `1` at or above the warning threshold, and `2` when limits are not configured.

## Rollback

The OpenClaw installer creates `~/.openclaw/openclaw.json.narratiive-backup` before changing the live configuration. The runtime environment must also be copied to a timestamped, mode-600 backup before limit values are added. Rollback is to restore those two backups and restart only the OpenClaw gateway and Tony HTTP bridge.
