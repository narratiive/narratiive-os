# Narratiive Mission Control

Mission Control V1 is the private, read-only operator interface for Narratiive OS.
It projects the same tenant-scoped lead, workflow, event, artefact, approval and
health state used by Tony. It does not maintain a lifecycle database or a second
workflow state.

## Local access

Bookmark:

```text
http://127.0.0.1:8790/mission-control
```

The route is served by `com.narratiive.tony-http-bridge` on loopback only. It
starts automatically with the existing Narratiive OS LaunchAgent and after a
Mac restart or user login. The page polls its read-only projection every ten
seconds and marks unavailable state visibly. Synthetic and suppressed fixtures
are labelled `TEST` and excluded from the default executive counts.

Health check:

```bash
curl -fsS http://127.0.0.1:8790/health
```

The JSON projection is available locally at
`http://127.0.0.1:8790/mission-control/api`. It contains no approval tokens or
credentials. Artefact links are offered only for files that resolve inside the
configured workflow runtime root.

## Start, deploy and recover

The canonical deployment command installs or reloads the existing services and
then runs the operational checks:

```bash
zsh ~/Documents/narratiive-os/scripts/deploy_narratiive_os.sh
```

If only the Tony bridge is unavailable, safely restart its existing LaunchAgent:

```bash
launchctl kickstart -k "gui/$(id -u)/com.narratiive.tony-http-bridge"
```

No additional Mission Control daemon, database or manual startup step exists.
Workflow and artefact truth survives restarts because it remains in the
canonical durable runtime stores; the interface is rebuilt from those stores on
every read.

## Security and authority

V1 binds to the Tony bridge's configured loopback address and also rejects
non-loopback requests at the application boundary. It has GET routes only.
There are no UI paths for approval, client communication, publication, media
mutation, spend or any other external action. Matt must use the existing
governed Tony flow for a displayed decision, preserving exact artefact binding,
approval language and action gates.

The browser receives no API keys, tokens, environment values or raw approval
tokens. The main local threat is another process running as Matt's macOS user;
V1 does not claim to isolate against a compromised local account.

## Future remote access

Remote access is deliberately disabled. A later version should sit behind an
authenticated, TLS-terminating private access layer with explicit identity,
session expiry, CSRF protection, audit evidence and the same workspace scope.
It must not expose the loopback service directly to the public internet.

