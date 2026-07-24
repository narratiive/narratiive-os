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

To enable Tony's read-only GitHub awareness for one repository, also configure:

```text
TONY_GITHUB_REPOSITORY=narratiive/narratiive-os
TONY_GITHUB_WORKSPACE_ID=agency
TONY_GITHUB_MATT_LOGIN=replace-with-matts-github-login
TONY_GITHUB_TOKEN=replace-with-read-only-token
```

The named workspace must already exist under `NARRATIIVE_RUNTIME_ROOT`. Use a
fine-grained token limited to the configured repository with read access to
metadata, pull requests, issues and checks. Tony performs only `GET` requests.
If any setting is absent, the capability is reported as `not_connected`. API
errors, invalid responses and incomplete pagination are reported as degraded;
cached observations are never presented as live.

Optional controls are `TONY_GITHUB_API_URL`,
`TONY_GITHUB_TIMEOUT_SECONDS` and `TONY_GITHUB_MAX_PAGES`. The API URL must use
HTTPS. Credentials remain in the external mode-`0600` environment file and are
not written to events, artefacts or command responses.

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
