# Tony inbound runtime readiness

Status: operational acceptance companion for Growth Diagnostic → Blueprint Lite

## Purpose

This checklist distinguishes three different truths that must not be collapsed:

1. the lead was captured and persisted;
2. Tony accepted and knows the lead;
3. Tony actually progressed the lead into Blueprint Lite preparation and human review.

A `200` response from `/leads/ingest` proves lead acceptance. The response now also exposes the initial Blueprint Lite preparation state, but later states such as `awaiting_review` still require durable runtime evidence.

## Canonical path

`Website Growth Diagnostic → n8n → Notion Leads — CANONICAL → Tony /leads/ingest → Blueprint Lite preparation → human review → approved delivery → Discovery`

The canonical recipient-facing product contract is `products/blueprint-lite/README.md`.

## Required live configuration

### Tony bridge

The secure runtime environment must contain a non-empty `TONY_BRIDGE_TOKEN`. n8n must send the same secret as `Authorization: Bearer <token>`.

The bridge must be healthy on the configured host/port before any downstream test. Lead ingestion requires the bearer credential even on loopback traffic.

### Claude preparation

Tony's direct Claude worker is fail-closed and must be explicitly enabled. Required settings are:

- `TONY_DISPATCH_CLAUDE_MODE=anthropic_api`
- `TONY_DISPATCH_CLAUDE_MODEL=<approved model id>`
- either `ANTHROPIC_API_KEY` or `TONY_DISPATCH_CLAUDE_API_KEY`

Credentials alone do not enable the dispatcher. If the mode is absent, Tony records `dispatcher_unavailable` rather than claiming preparation happened.

### Blueprint Lite durable state

`TONY_BLUEPRINT_LITE_PREPARATION_PATH` may override the default internal runtime state file. The default is `.runtime/blueprint-lite-preparation.json` inside Narratiive OS.

The state file is an internal projection, not a client-facing artefact and not a replacement for Notion. It contains the exact inbound input package Tony received, its stable fingerprint, the bounded Claude dispatch contract, quality-gate evidence and any internal Blueprint Lite versions.

### Downstream consequential tools

Later stages may require explicitly configured dispatch surfaces for Gmail, Google Calendar, Notion, Google Drive and Fireflies. Missing worker configuration must fail closed and surface the exact blocker. Consequential writes remain approval-gated even when a worker is configured.

## Repository control boundary

The event-driven runtime now queues Blueprint Lite preparation directly from an accepted Growth Diagnostic lead instead of requiring the conversational `what should I focus on? → OK, do that` path.

The ingress request does not wait for Claude. Tony persists one preparation job keyed to lead identity and an input fingerprint, returns the current preparation state to n8n, and starts a bounded daemon worker when Claude is explicitly configured. This avoids coupling n8n's webhook timeout to model latency.

The worker:

1. consumes Tony's existing `TonyExecutiveToolRouter` to obtain the safe Claude `autonomous_prepare` dispatch contract;
2. uses the already configured Claude dispatcher rather than a second execution surface;
3. uses Tony's existing autonomous evidence verifier before accepting returned work;
4. applies a Blueprint Lite-specific quality gate;
5. requires Claude to state whether the received diagnostic package is complete enough to represent the diagnostic faithfully;
6. versions only decision-grade Blueprint Lite evidence;
7. stops at `awaiting_review` with `approval_required=true`;
8. performs no email, Drive share, Notion delivery mutation, Calendar booking or other consequential client action.

On runtime restart, durable `preparation_queued` work is recovered. A job left in `dispatching` by a process interruption is returned to the queue and retried; a previously unavailable Claude dispatcher is retried when the runtime restarts with valid configuration. Failed or unverified model attempts remain blocked for inspection rather than being repeatedly redriven automatically.

## Acceptance criteria

A production inbound test is fully accepted only when all of the following are evidenced:

1. the website stores the submission once;
2. n8n creates exactly one canonical Notion lead;
3. Tony upserts exactly one durable lead projection;
4. Tony creates or recovers one Blueprint Lite preparation state keyed to stable lead/submission identity;
5. `/leads/ingest` returns quickly with `preparation_status` rather than waiting for Claude;
6. Tony autonomously dispatches only the bounded Claude preparation task when configured;
7. Claude returns decision-grade structured evidence and no consequential external mutation;
8. Tony validates the return against the Blueprint Lite quality gate;
9. the exact internal artefact is versioned and enters `awaiting_review`;
10. no email/share/CRM delivery state/Calendar booking occurs before scoped human approval;
11. delivery is claimed only after exact execution evidence;
12. exact replay creates no duplicate lead, Claude job, artefact or send.

## Operational interpretation

Use these states consistently:

- `lead_ingested` — Tony has accepted and persisted the lead projection.
- `preparation_queued` — a durable Blueprint Lite job exists and is eligible for the background preparation worker.
- `dispatcher_unavailable` — preparation is blocked by missing Claude worker configuration.
- `dispatching` — the bounded internal Claude preparation call is currently in progress; this is not delivery.
- `dispatch_failed` or `dispatch_unverified` — a worker attempt occurred but did not satisfy the execution/evidence contract.
- `blocked` — a deterministic safety or Blueprint Lite quality gate prevented progression; inspect `blocker` and `failed_checks`.
- `awaiting_review` — a versioned Blueprint Lite passed Tony's internal quality gate and is waiting for human approval.
- `approved_pending_delivery` — scoped approval exists but client-facing delivery is not yet evidenced.
- `delivered` — the exact approved artefact has verified recipient-facing execution evidence.

Never infer a later state from an earlier one.

## Production status

The repository implementation is not production-accepted until the Mac runtime is updated/restarted and a fresh labelled Growth Diagnostic demonstrates the acceptance chain above. In particular, the production n8n payload must be checked to confirm it contains enough diagnostic evidence for `diagnostic_input_coverage.complete=true`. If it does not, Tony must block at the quality gate and the n8n handoff must be enriched rather than allowing Claude to infer missing inputs.
