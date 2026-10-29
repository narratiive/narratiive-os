# Tony conversational Discovery approval and founder briefings

Issue #499 implementation scope: Worker Infrastructure (`runtime/`, `openclaw/`,
`tests/`). Discovery specialist ownership, product canon and external-action
approval contracts remain unchanged. The copied trusted-owner instruction is the
specification; this change does not depend on unmerged PR #498.

The bounded phrase “Loom Loft is approved for Discovery” enters through the
existing authenticated Telegram bridge with the configured founder principal.
The poller routes this phrase directly to that boundary. Matching is insensitive
to case, whitespace and trailing full stops/exclamation marks; conditional or
extended instructions do not match this deterministic approval path.

Exactly one pending authoritative Loom Loft gate must exist, and it must be the
Blueprint Lite gate preceding Discovery preparation. Otherwise Tony asks one
short clarification without requesting identifiers. The token is resolved
internally, and its artefact/gate binding is checked again under the existing run
lock before the approval is persisted. The original human instruction and exact
binding are recorded in approval history.

After approval, only Discovery preparation is commissioned through the existing
durable worker. Duplicate instructions do not approve a later gate or create a
second run. A saved approval whose commissioning failed can retry that handoff
using its recorded binding. A handoff failure acknowledges the saved approval
and reports the blocker. Sending, booking and subsequent gates remain separate.
The existing conversation worker must be running to execute queued preparation;
this change does not install or start a service.

Morning and evening compact brief renderings share a maximum of three unique
founder decisions or delivery risks. Routine activity, background platform notes
and repeated recommendations are omitted; detailed structured briefs retain
their evidence. Runtime reference prefixes are removed from compact messages.
Internal review emails contain three concise lines and the existing immutable
PDF attachment. Proactive review messages include a link to the verified Gmail
review receipt, or report that review delivery could not be verified.

Local acceptance uses synthetic Loom Loft fixtures and injected workers/senders,
with no Telegram, provider or other external calls. Live Telegram acceptance is
still a founder-controlled gate. Independent review and founder acceptance are
outstanding; this worktree does not create or merge a PR, deploy, or release work.
