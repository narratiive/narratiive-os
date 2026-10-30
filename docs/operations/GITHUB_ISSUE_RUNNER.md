# GitHub issue runner

The runner processes one open `narratiive/narratiive-os` Issue labelled
`agent:ready` at a time. It changes that label to `agent:claimed` when claimed, runs Codex without
GitHub credentials or network access in an isolated worktree, pushes the
verified branch, creates a **draft** pull request, records bounded evidence, and
moves the Issue to `agent:review`. A safe failure is commented and labelled
`agent:blocked`. `agent:done` is reserved for the existing human-controlled
post-merge process; this runner never applies it. It never merges, deploys, releases, sends messages, or treats
arbitrary comments as instructions.

## Configure

Copy `github-issue-runner.config.example.json` outside the repository to:

```text
~/.config/narratiive/github-issue-runner.json
```

Set the paths and trusted GitHub owner login. The JSON contains policy only and
must contain no token. The runner uses the Mac Mini's existing authenticated
GitHub CLI session; do not add a token to this file or to the service plist.
Set `github_cli_executable` to the absolute local `gh` path so the LaunchAgent
does not depend on an interactive-shell PATH. Set `github_home` to the local
account home directory so the runner can locate that existing CLI session even
though launchd does not define `HOME`.
Set `codex_home` to the existing private Codex home directory. The runner
prepends the configured Codex executable's directory to its child-only PATH,
which supplies Node for the Codex script under launchd.
Keep branch protection as the independent merge gate. The runner has no merge
command, and the local Codex child receives an allowlisted environment that
excludes GitHub token variables.

Create the labels `agent:ready`, `agent:claimed`, `agent:review`,
`agent:blocked`, and `agent:done` before
enabling the service. A trusted-owner comment is included only when it begins
exactly with `/agent-follow-up `; at most three such comments and 2,000
characters each are accepted. All other comments are ignored except for the
runner's own idempotency marker.

## Validate once and install

From the canonical checkout:

```bash
.venv/bin/python scripts/run_github_issue_runner.py \
  --config "$HOME/.config/narratiive/github-issue-runner.json" --once

.venv/bin/python scripts/install_launch_agents.py \
  --python .venv/bin/python \
  --env-file "$HOME/.config/narratiive/runtime.env" \
  --github-issue-runner-config "$HOME/.config/narratiive/github-issue-runner.json"
```

Inspect the service and logs with:

```bash
launchctl print "gui/$(id -u)/com.narratiive.github-issue-runner"
tail -f "$HOME/Library/Logs/Narratiive/com.narratiive.github-issue-runner.err.log"
```

State is under the configured per-repository state directory. `events.jsonl` is
append-only; `state.json` is its atomic current-state projection. The runner
holds a non-blocking OS lock for each poll-to-transition sequence, so only one
writer can claim or advance work. After a restart it resumes the recorded stage,
reuses the issue branch and draft PR, and blocks rather than rerunning an
ambiguous dirty worktree.

For each Codex attempt, private mode-`0600` stdout and stderr logs are retained
under the configured state directory and referenced in the durable run state.
Only hashes and byte counts are posted to GitHub.

To stop and remove all repository LaunchAgents, use the existing installer
`--uninstall` command. Removing the runner plist does not delete worktrees,
logs, or evidence. Review those records before manual cleanup.
