# Tony Evening Workflow and Chat Handoff

Date: 27 July 2026

## Current state

The Telegram delivery path is now functional end to end:

Telegram Trigger -> HTTP POST `http://127.0.0.1:8790/telegram` -> Format Tony Response -> Telegram Send Message.

The live services are healthy:

- Narratiive runtime gateway on port 8787
- Tony HTTP bridge on port 8790
- Deployment receipt current
- Legacy bridge removed

The `/morning` command now returns successfully in Telegram. The remaining problem is not transport. It is quality and operational awareness: Tony currently produces a technically correct but largely empty brief because Mission Control has insufficient live workstream, GitHub, progress, blocker and approval data.

## Evening objective

Move Tony from a system-status responder to a constructive, proactive Chief of Staff.

The evening work should deliver four outcomes:

1. Improve the structure and tone of `/morning` and `/evening`.
2. Connect those briefs to real operating data.
3. Separate business priorities from technical health warnings.
4. Establish a repeatable handoff between chats and repository work.

## Workstream A — Executive brief redesign

Replace the current flat diagnostic output with a compact structure:

### Morning brief

- Today's focus
- What moved since the previous brief
- What Tony is handling
- Decisions or approvals needed from Matt
- Blockers
- System watch-outs

### Evening review

- What was completed
- What moved forward
- What remains open
- What Tony will carry into tomorrow
- Decisions needed
- System watch-outs

Rules:

- Never allow a routine connection warning to dominate the briefing.
- Use plain managerial language, not system-policy wording.
- Omit empty sections.
- Maximum three priorities.
- Maximum five open items.
- State clearly when Tony has no trusted data rather than filling gaps.

## Workstream B — Operational awareness

Tony's briefs should combine:

- Narratiive workstreams and owners
- GitHub issues and pull requests
- completed work since the previous brief
- current blockers
- pending approvals
- Tony's next planned actions
- live service health, demoted to a final watch-outs section

The brief must distinguish:

- business blocker
- engineering blocker
- workflow approval
- external dependency
- system health warning

## Workstream C — Proactive Chief of Staff behaviour

Tony should not merely describe state. He should recommend the next move and say what he will do next.

Each brief should include:

- `Tony's recommendation`
- `Tony is handling`
- `Your input needed`

Tony should only interrupt Matt for:

- irreversible decisions
- credentials or account access
- commercial commitments
- client-facing approvals
- material reprioritisation

Everything else should remain queued, progressed or reported without interruption.

## Workstream D — Continuity between chats

The repository is the source of truth. Every productive chat working on Tony should leave behind:

1. a concise operating-state update;
2. repository changes or issue references;
3. verified evidence of what works;
4. unresolved blockers;
5. the exact next action.

The next chat should begin by reading this document and checking the current repository state before proposing new work.

## Verified evidence from this session

- Old bridge and new bridge were previously competing.
- The live installation has now been consolidated around `narratiive-os`.
- `NARRATIIVE_API_KEY` was added to the runtime environment.
- Service doctor returned healthy for runtime gateway, Tony bridge and deployment state.
- Direct POST to port 8790 returned a complete `/morning` payload.
- n8n was corrected from port 8787 to port 8790.
- Telegram output field was corrected from `reply` to `telegram_text` after formatting.
- A full `/morning` response was successfully delivered in Telegram.

## Immediate next implementation sequence

1. Redesign `ExecutiveBrief.render_compact()`.
2. Add a dedicated `system_watchouts` section.
3. Prevent empty Mission Control state from producing pseudo-strategic wording.
4. Improve Mission Control ingestion of active workstreams.
5. Reconnect or configure GitHub awareness.
6. Add tests for high-value morning and evening output.
7. Validate `/morning`, `/evening`, `/status`, `/client` in Telegram.

## Definition of done for the next cycle

A successful `/morning` response should let Matt understand, in under 30 seconds:

- what matters today;
- what changed;
- what Tony is doing;
- what is blocked;
- whether Matt needs to act.

It should not read like a diagnostic log.

## New chat kickoff prompt

Use this in a new chat:

> Continue the Tony Chief of Staff build in `narratiive/narratiive-os`. Start by reading `docs/operations/tony-evening-handoff-2026-07-27.md`, then inspect the current implementation before making changes. The Telegram transport is working. The immediate objective is to turn `/morning` and `/evening` into concise, constructive executive briefs grounded in real workstreams, GitHub activity, blockers, approvals and Tony's own next actions. Work proactively in the repository, avoid duplicating existing workstreams, and only interrupt me for a genuine blocker or decision.
