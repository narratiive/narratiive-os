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
TONY_EXECUTIVE_WORKSPACE_ID=agency
NARRATIIVE_RUNTIME_RESTART_COMMAND=["launchctl","kickstart","-k","gui/501/com.narratiive.runtime"]
TONY_BRIDGE_RESTART_COMMAND=["launchctl","kickstart","-k","gui/501/com.narratiive.tony-http-bridge"]
NARRATIIVE_SUPERVISOR_EVENT_LOG=/Users/you/Library/Logs/Narratiive/supervisor.jsonl
```

Use the actual user ID returned by `id -u` in the restart commands. Secrets are never copied into plist files. `scripts/run_with_env.py` reads the mode-600 environment file without invoking a shell, then replaces itself with the target process.

`TONY_EXECUTIVE_WORKSPACE_ID` selects the existing workspace used for immutable
morning and evening brief artifacts. If it is omitted, briefs use the legacy
local runtime. This archive remains available whether or not GitHub awareness
is configured.

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

The GitHub and executive brief workspace IDs must match. For compatibility,
`TONY_GITHUB_WORKSPACE_ID` also selects the brief workspace when
`TONY_EXECUTIVE_WORKSPACE_ID` is omitted. Invalid GitHub configuration leaves
the rest of Tony available and reports GitHub as `not_connected`.

Optional controls are `TONY_GITHUB_API_URL`,
`TONY_GITHUB_TIMEOUT_SECONDS` and `TONY_GITHUB_MAX_PAGES`. The API URL must use
HTTPS. Credentials remain in the external mode-`0600` environment file and are
not written to events, artefacts or command responses.

To enable the approved Engineering Task pipeline, keep the read token above and
add a separate fine-grained token:

```text
TONY_GITHUB_ISSUE_TOKEN=replace-with-issues-write-only-token
TONY_GITHUB_REQUIRED_CHECKS=runtime-tests
TONY_GITHUB_REQUIRED_REVIEWERS=replace-with-matts-github-login
```

The Issue token must be restricted to the configured repository with only
Metadata read and Issues read/write. It must not have Contents, Pull Requests,
Actions, Workflows, Deployments or Administration write access. GitHub grants
Issues permission at repository scope rather than per Issue, so Tony enforces
the narrower task-to-Issue binding in the application and exposes only Issue
creation and bound-Issue comments.

`TONY_GITHUB_MATT_LOGIN` is also the engineering-task approver allowlist.
Unapproved tasks, a different reviewer, modified approved content, missing
required-check configuration, stale reviews and unknown mergeability all fail
closed. Tony never creates branches or pull requests, approves reviews, closes
Issues or invokes a merge endpoint.

Optional local Codex dispatch is enabled only when all of the following policy
settings are present:

```text
TONY_ENGINEERING_EXECUTION_POLICY_VERSION=1
TONY_ENGINEERING_ALLOWED_PATHS=runtime/**,tests/**,schemas/**
TONY_ENGINEERING_VERIFICATION_PROFILE=runtime-tests
TONY_ENGINEERING_BASE_REF=main
TONY_ENGINEERING_TIMEOUT_SECONDS=1800
TONY_ENGINEERING_MAX_ATTEMPTS=2
TONY_CODEX_EXECUTABLE=codex
```

Only the built-in `runtime-tests` verification profile is accepted. Tony does
not execute command strings, prompts, paths or environment values supplied
through the public command payload. Codex runs without GitHub credentials or
sandbox network access in an isolated worktree under the workspace runtime
root. Successful execution produces a verified local commit and immutable
evidence only; branch push and Pull Request creation remain manual.

## Proactive executive delivery (no Telegram command required)

`scripts/run_proactive_brief.py` reuses the existing `/morning` and `/evening`
executive brief service and Mission Control projection to send one proactive
message to Matt through the Telegram Bot API, without Matt issuing a command
first. It also checks Mission Control for new blockers or approvals that
require Matt and escalates them as one deduplicated, rate-limited message.
This does not add a new dashboard, state engine or source of truth: generation
still goes through `TonyExecutiveCommandService` and the same brief archive
and Mission Control loaders the Telegram bridge already uses.

Configure outbound delivery in the same secure environment file:

```text
TONY_TELEGRAM_BOT_TOKEN=replace-with-a-bot-token-scoped-to-this-bot-only
TONY_TELEGRAM_CHAT_ID=replace-with-matts-telegram-chat-id
```

Optional controls:

```text
TONY_TELEGRAM_API_BASE=https://api.telegram.org
TONY_TELEGRAM_TIMEOUT_SECONDS=10
TONY_PROACTIVE_MAX_ATTEMPTS=3
TONY_PROACTIVE_ESCALATION_MIN_INTERVAL_SECONDS=1800
```

`TONY_EXECUTIVE_WORKSPACE_ID` (already required for the brief archive) selects
the workspace whose durable delivery-key store, escalation store and Mission
Control connection status the script reads and writes. A repeated invocation
for the same workspace, command and calendar date does not resend; a repeated
escalation for the same set of blockers/approvals does not resend either.
Missing bot token, chat id or workspace configuration fails closed: the script
exits non-zero, records an immutable `configuration_blocked` event, and marks
the `proactive-delivery` Mission Control connection `degraded` so a failure is
an actionable blocker rather than a silent no-op.

Two overlapping invocations for the same workspace (a manual run overlapping
a scheduled one, or two schedulers misconfigured to both fire) cannot both
pass duplicate suppression and send: each invocation takes an exclusive,
non-blocking OS file lock at
`<workspace runtime root>/proactive-delivery/proactive.lock` for the
duration of its duplicate-check-to-evidence sequence. A contending
invocation exits `0` with status `already_running` and sends nothing; it
does not wait for the first to finish. The lock is released automatically
on normal completion, on an unhandled exception, and on process crash (the
kernel releases an `flock` held by a process that exits), so there is no
stale-lock file to clean up. Separate workspaces use separate lock files and
never contend with each other. If the lock file itself cannot be opened
(for example an unwritable directory), the script fails closed with status
`lock_unavailable` and marks the Mission Control connection `degraded`,
distinct from ordinary benign contention.

Run it directly for a manual or externally triggered send:

```bash
.venv/bin/python scripts/run_proactive_brief.py --mode brief --command morning
.venv/bin/python scripts/run_proactive_brief.py --mode escalation
```

`--mode both` (the default) runs the brief and the escalation check in one
invocation, which is the intended shape for a scheduled trigger. To schedule
it with launchd, add a fourth per-user LaunchAgent with a fixed
`StartCalendarInterval` (for example `{"Hour": 8, "Minute": 0}` and
`{"Hour": 18, "Minute": 0}` as two array entries for morning and evening)
running:

```text
scripts/run_with_env.py <env-file> <python> scripts/run_proactive_brief.py --mode both --command morning
```

This is deliberately not wired into `scripts/install_launch_agents.py` yet:
the existing installer's three agents are covered by
`tests/test_launchd_installer.py` and installing a fourth agent changes what
runs unattended on Matt's machine, which should be a separate, explicit
decision once the delivery cadence is confirmed. Use
`--simulate-transport-failure` only for smoke validation; it forces a
transient send failure so the bounded-retry and fail-closed path can be
observed without waiting for a real outage.

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
