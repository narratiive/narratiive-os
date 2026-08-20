# OpenClaw Gateway auth resolution

The live Mac proved that the Tony fleet and Ollama model were healthy while `/v1/responses` still returned HTTP 401. The cause was architectural: Narratiive's Tony ingress and acceptance probe only looked for `OPENCLAW_GATEWAY_TOKEN` in their own process environment, while OpenClaw can legitimately keep Gateway auth in its active config.

This change keeps OpenClaw as the conversational runtime and removes that duplicate secret-plumbing requirement.

- Process `OPENCLAW_GATEWAY_TOKEN` or `OPENCLAW_GATEWAY_PASSWORD` still wins.
- Otherwise Narratiive resolves the active OpenClaw config path using `OPENCLAW_CONFIG_PATH`, `OPENCLAW_STATE_DIR`, `OPENCLAW_HOME`, or the normal `~/.openclaw/openclaw.json` default.
- `gateway.auth.mode=token` and `gateway.auth.mode=password` are both sent as Bearer credentials, matching OpenClaw's HTTP Gateway contract.
- Literal `${ENV}` references and simple env-backed SecretRefs are supported without logging the resolved secret.
- `gateway.auth.mode=none` sends no Authorization header.
- Tony's live Telegram bridge uses this resolver automatically through `TonyAgentGatewayConfig.from_env`.
- `scripts/check_tony_openclaw_live_authenticated.py` provides a safe acceptance entrypoint that reports only whether auth was found and where it came from, never the credential.

No phrase-specific routing is added. Narratiive OS remains the control plane; OpenClaw remains the natural-language and multi-agent layer.
