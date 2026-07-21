# Operational acceptance check

After installing or upgrading the macOS LaunchAgents, run:

```bash
python3 scripts/operational_acceptance.py
```

The command validates:

- the local Narratiive environment file exists and is mode `0600`;
- the runtime health endpoint returns HTTP 200 with `{"ok": true}`;
- the Tony bridge health endpoint returns HTTP 200 with `{"ok": true}`;
- all three expected LaunchAgents are loaded in the current user's `launchd` domain.

It prints one JSON report and exits `0` only when the installation is operationally ready. A failed check exits `1`, making the command safe for scripts and deployment verification.

Default locations and endpoints:

```text
~/.config/narratiive/runtime.env
http://127.0.0.1:8787/health
http://127.0.0.1:8790/health
```

Override them when necessary with:

```bash
export NARRATIIVE_ENV_FILE="$HOME/.config/narratiive/runtime.env"
export NARRATIIVE_RUNTIME_HEALTH_URL="http://127.0.0.1:8787/health"
export TONY_BRIDGE_HEALTH_URL="http://127.0.0.1:8790/health"
```

A `not_ready` result should be treated as an installation or service incident. Inspect the individual `checks` entries before restarting anything manually; the service supervisor may already be applying the narrow recovery policy.
