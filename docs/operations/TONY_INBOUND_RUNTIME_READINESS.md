# Tony inbound runtime readiness

Status: operational acceptance companion for Growth Diagnostic → Blueprint Lite

## Purpose

This checklist distinguishes three different truths that must not be collapsed:

1. the lead was captured and persisted;
2. Tony accepted and knows the lead;
3. Tony actually progressed the lead into Blueprint Lite preparation and human review.

A `200` response from `/leads/ingest` proves only the second boundary unless preparation state and verified worker evidence are also present.

## Canonical path

`Website Growth Diagnostic → n8n → Notion Leads — CANONICAL → Tony /leads/ingest → Blueprint Lite preparation → human review → approved delivery → Discovery`

The canonical recipient-facing product contract is `products/blueprint-lite/README.md`.

## Required live configuration

### Tony bridge

The secure runtime environment must contain a non-empty `TONY_BRIDGE_TOKEN`. n8n must send the same secret as `Authorization: Bearer <token>`.

The bridge must be healthy on the configured host/port before any downstream test.

### Claude preparation

Tony's direct Claude worker is fail-closed and must be explicitly enabled. Required settings are:

- `TONY_DISPATCH_CLAUDE_MODE=anthropic_api`
- `TONY_DISPATCH_CLAUDE_MODEL=<approved model id>`
- either `ANTHROPIC_API_KEY` or `TONY_DISPATCH_CLAUDE_API_KEY`

Credentials alone do not enable the dispatcher. If the mode is absent, Tony must report a dispatcher blocker rather than claim preparation happened.

### Downstream consequential tools

Later stages may require explicitly configured dispatch surfaces for Gmail, Google Calendar, Notion, Google Drive and Fireflies. Missing worker configuration must fail closed and surface the exact blocker. Consequential writes remain approval-gated even when a worker is configured.

## Current control boundary

As of 31 August 2026, production acceptance proved:

- website persistence;
- one n8n webhook handoff;
- one canonical Notion lead;
- authenticated Tony bridge acceptance;
- Tony response `status=lead_ingested`.

The live `LeadAwareTonyApplication._ingest()` path currently persists the inbound lead and returns immediately. It does not itself prove or trigger Blueprint Lite preparation. Issue #305 tracks the required event-driven orchestration boundary.

## Acceptance criteria

A production inbound test is fully accepted only when all of the following are evidenced:

1. the website stores the submission once;
2. n8n creates exactly one canonical Notion lead;
3. Tony upserts exactly one durable lead projection;
4. Tony creates or recovers one Blueprint Lite preparation state keyed to stable lead/submission identity;
5. Tony autonomously dispatches only the bounded Claude preparation task when configured;
6. Claude returns decision-grade structured evidence and no consequential external mutation;
7. Tony validates the return against the Blueprint Lite quality gate;
8. the exact artefact is versioned and enters `Awaiting Review`;
9. no email/share/CRM delivery state/Calendar booking occurs before scoped human approval;
10. delivery is claimed only after exact execution evidence;
11. exact replay creates no duplicate lead, job, artefact or send.

## Operational interpretation

Use these states consistently:

- `lead_ingested` — Tony has the lead; no claim about Blueprint Lite preparation.
- `preparation_queued` — a durable Blueprint Lite job exists but has not returned verified work.
- `dispatcher_unavailable` — preparation is blocked by missing worker configuration.
- `dispatch_failed` or `dispatch_unverified` — a worker attempt occurred but did not satisfy the evidence contract.
- `awaiting_review` — a versioned Blueprint Lite passed Tony's internal quality gate and is waiting for human approval.
- `approved_pending_delivery` — scoped approval exists but client-facing delivery is not yet evidenced.
- `delivered` — the exact approved artefact has verified recipient-facing execution evidence.

Never infer a later state from an earlier one.
