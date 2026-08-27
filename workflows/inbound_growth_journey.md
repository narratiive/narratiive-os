# Inbound Growth Journey

Status: Canonical execution contract
Version: 1.0
Decision: Matt, 27 August 2026

## Objective

Run one coherent customer journey from the website Growth Diagnostic to a commissioned Growth Sprint and full Growth Blueprint, without duplicate products, ambiguous promises or silent handoff failures.

Canonical journey:

`Growth Diagnostic → Blueprint Lite → Discovery → Growth Sprint → Growth Blueprint → Campaign World`

## System ownership

- **Replit website** captures diagnostic inputs, shows the immediate Growth Diagnostic result and creates the lead submission.
- **PostgreSQL / lead record** persists the exact diagnostic inputs and server submission timestamp.
- **n8n** transports the lead event and external-service actions where configured.
- **Narratiive OS / Tony** owns state, orchestration, retries, exceptions, validation and human-review routing.
- **Claude** performs authorised Blueprint Lite research/reasoning/drafting and post-Discovery proposal drafting.
- **Notion** is the commercial/client source of truth where the existing integration is configured.
- **Google Drive** stores recipient-facing artefacts and approved source material.
- **Gmail** sends approved recipient-facing communications.
- **Google Calendar** owns Discovery booking/events.
- **Fireflies** captures the Discovery meeting where configured.
- **Human approver** approves Blueprint Lite and the commercial proposal before release.

## Required states

1. `diagnostic_completed`
2. `lead_persisted`
3. `blueprint_lite_queued`
4. `blueprint_lite_generating`
5. `blueprint_lite_ready_for_review`
6. `blueprint_lite_changes_requested`
7. `blueprint_lite_approved`
8. `blueprint_lite_sent`
9. `awaiting_discovery`
10. `discovery_booked`
11. `discovery_complete`
12. `proposal_generating`
13. `proposal_ready_for_review`
14. `proposal_approved`
15. `proposal_sent`
16. `growth_sprint_accepted`
17. `growth_blueprint_commissioned`

All transitions must be idempotent. Replaying an event must not create duplicate lead records, duplicate Blueprint Lite artefacts, duplicate emails or duplicate calendar events.

## Step 1 — Growth Diagnostic

The website calculates and displays the immediate Growth Diagnostic result.

Requirements:

- preserve the current scoring model unless deliberately versioned;
- collect all answers used downstream;
- distinguish the instant Growth Diagnostic result from Blueprint Lite;
- never claim a Blueprint Lite or report was sent before downstream confirmation;
- record analytics for completion, result viewed and downstream request state.

## Step 2 — Lead persistence and Tony trigger

A named/email submission must:

- persist the lead and raw answers;
- create a stable lead ID;
- emit one downstream event with `source=growth_diagnostic`;
- include company, website, diagnostic scores, blockage, recommended actions and all raw answers;
- enqueue Blueprint Lite generation;
- create/update the Notion lead/company record where configured.

Failure rule: persistence failure is user-visible and retryable. Downstream delivery failure must not erase the persisted lead.

## Step 3 — Blueprint Lite generation

Tony routes the approved input package to Claude under `products/blueprint-lite/README.md`.

Inputs combine:

- the prospect's diagnostic inputs;
- the stored diagnostic result;
- selective outside-in public research;
- prior approved prospect context where available.

Output must follow the canonical 7-part Blueprint Lite structure and retain evidence lineage.

## Step 4 — Human quality gate

Tony sets `blueprint_lite_ready_for_review` and sends one review notification containing:

- prospect/company;
- diagnostic summary;
- Blueprint Lite link;
- quality status;
- approve / changes-required action.

No recipient-facing dispatch occurs without recorded human approval for the exact artefact version.

## Step 5 — Blueprint Lite delivery

On approval:

- save/finalise the artefact in the prospect/client Drive folder;
- prepare a concise personalised email;
- send via Gmail only after approval;
- record message ID, artefact version, sent timestamp and recipient;
- set `awaiting_discovery`;
- present Discovery as the next step.

## Step 6 — Discovery

When Discovery is booked:

- create/resolve the Calendar event;
- attach the relevant prospect/client identity;
- update state to `discovery_booked`;
- use Fireflies capture where the configured workspace permits it.

After the call, store a structured summary containing:

- commercial problem;
- desired outcome;
- relevant internal context;
- decision-makers;
- urgency/timing;
- budget signals without inventing a budget;
- evidence that changes or strengthens Blueprint Lite hypotheses;
- recommended scope;
- open questions;
- next action.

## Step 7 — Bespoke Growth Sprint proposal

Claude drafts a proposal using the Diagnostic, Blueprint Lite and Discovery evidence.

The proposal must be personal rather than a generic capabilities deck and should frame:

- what we heard;
- what we now believe the full Growth Blueprint needs to answer;
- scope of the Growth Sprint;
- expected Growth Blueprint deliverables;
- timeline;
- exact proposed investment within the authorised £3,000–£8,000 range;
- assumptions/dependencies;
- clear acceptance path.

Price selection is a recommendation until approved by the authorised human.

## Step 8 — Acceptance and commissioning

On recorded client acceptance:

- set `growth_sprint_accepted`;
- create the Growth Blueprint commission using the canonical premium product contract;
- retain lineage to the originating Diagnostic, Blueprint Lite, Discovery summary and accepted proposal;
- set `growth_blueprint_commissioned`;
- hand off to the existing Growth Blueprint pipeline.

## Reliability contract

Every external action must have:

- idempotency key;
- bounded timeout;
- retry policy for transient failures;
- durable failure/error state;
- human-readable exception notification after retry exhaustion;
- audit record containing event, target service, attempt count and final result.

Never show a customer a success promise merely because an asynchronous request was queued.

## Permission checks

Before production release, verify the runtime can:

- receive the Replit diagnostic webhook;
- create/update the commercial lead record;
- invoke the Claude generation path assigned by the product contract;
- create/update the intended Google Drive artefact;
- draft/send through the intended Gmail account;
- create/read Discovery Calendar events;
- ingest Fireflies meeting output where configured.

Credentials and tokens must remain outside source control.

## Acceptance tests

At least three safe dummy submissions are required before production release:

1. normal qualified company with complete website/email;
2. low-information lead with no website and minimal optional answers;
3. downstream-failure case proving the customer is not falsely told that Blueprint Lite was sent.

For successful test cases prove:

`website submission → persisted lead → downstream event → Blueprint Lite generation → review gate → approved delivery → Discovery state → post-Discovery proposal state → Growth Sprint acceptance handoff fixture`

The test must verify no duplicate lead, artefact or email is created when the same event is replayed.
