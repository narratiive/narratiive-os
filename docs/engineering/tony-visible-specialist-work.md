# Tony visible specialist work

## Decision

Material specialist assignments should use OpenClaw's native persistent sub-agent session mode rather than a second Narratiive-owned specialist registry.

Tony should call `sessions_spawn` with `visible: true` and `category: "Narratiive specialists"` when Matt explicitly delegates work to Research, Strategy, Creative Director, Production or Operations, or when Tony expects to revisit, steer or report on the assignment later. Short disposable internal legwork can remain a hidden/default sub-agent run.

## Why

OpenClaw's current sub-agent contract makes `sessions_spawn` non-blocking and push-based. It also provides `visible: true` specifically for work the user will watch or return to; the persistent session returns ownership and session-receipt metadata and remains available as a durable specialist work surface. This is a better fit for Narratiive's named specialist team than inventing a parallel project/session registry in Narratiive OS.

Narratiive OS remains authoritative for business state, approvals, execution evidence, audit and deterministic consequences. OpenClaw remains authoritative for conversational context and specialist-session lifecycle.

## Acceptance

- explicit named-specialist assignments are persistent and revisitable;
- Tony stays responsive after the handoff rather than waiting synchronously;
- hidden sub-agents remain available for disposable internal legwork;
- an accepted spawn is reported as started/working, never completed;
- no phrase-specific routing or additional specialist state store is introduced.
