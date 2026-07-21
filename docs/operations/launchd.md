# Narratiive OS launchd installation

The repository can install three per-user macOS LaunchAgents:

- `com.narratiive.runtime` — authenticated Narratiive runtime gateway;
- `com.narratiive.tony-http-bridge` — Tony HTTP bridge for n8n and Telegram;
- `com.narratiive.service-supervisor` — health check and narrow recovery every 60 seconds.

## Secure environment file

Create a local file outside the repository:

```bash
mkdir -p "$HOME/.config/narratiive"
touch "$HOME/.config/narratiive/runtime.env"
chmod 600 "$HOME/.config/narratiive/runtime.env"
```

Required values normally include:

```text
NARRATIIVE_API_KEY=replace-me
TONY_BRIDGE_TOKEN=replace-me
NARRATIIVE_RUNTIME_RESTART_COMMAND=["launchctl","kickstart","-k","gui/501/com.narratiive.runtime"]
TONY_BRIDGE_RESTART_COMMAND=["launchctl","kickstart","-k","gui/501/com.narratiive.tony-http-bridge"]
NARRATIIVE_SUPERVISOR_EVENT_LOG=/Users/you/Library/Logs/Narratiive/supervisor.jsonl
```

Use the actual user ID returned by `id -u` in the restart commands. Secrets are never copied into plist files. `scripts/run_with_env.py` reads the mode-600 environment file without invoking a shell, then replaces itself with the target process.

## Install

Run from the repository using its virtual-environment Python:

```bash
.venv/bin/python scripts/install_launch_agents.py \
  --python .venv/bin/python \
  --env-file "$HOME/.config/narratiive/runtime.env"
```

The installer validates repository paths, Python, environment-file existence and secure permissions before writing or loading any agents.

Logs are written to:

```text
~/Library/Logs/Narratiive/
```

## Validate

```bash
launchctl print "gui/$(id -u)/com.narratiive.runtime"
launchctl print "gui/$(id -u)/com.narratiive.tony-http-bridge"
curl -fsS http://127.0.0.1:8787/health
curl -fsS http://127.0.0.1:8790/health
```

## Uninstall

```bash
.venv/bin/python scripts/install_launch_agents.py --uninstall
```

The environment file and logs are intentionally retained.
