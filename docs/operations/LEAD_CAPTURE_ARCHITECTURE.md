# Narratiive Lead Capture Architecture

## Decision

There is one commercial source of truth for prospects:

- Notion database: `Leads — CANONICAL`
- Database ID: `34b0c9cf-a8f2-80aa-9862-f05f4a65c676`
- Data source ID: `34b0c9cf-a8f2-80af-98e4-000b95243de6`

The older Leads database is legacy and must not receive new records.

## Principle

Every lead surface converges on the same two-write contract:

```text
Capture surface
  -> n8n capture
  -> Notion Leads — CANONICAL (source of truth)
  -> Tony POST /leads/ingest (synchronized executive state)
```

Notion owns the durable CRM record. Tony owns the live executive projection. A lead is not required to be qualified before Tony can see it.

Capture surfaces supply facts. Narratiive owns enrichment and commercial workflow defaults. Do not reproduce lead-temperature, pipeline-stage or next-action logic separately in every form.

For inbound Growth Diagnostic leads, the canonical customer journey is:

`Growth Diagnostic → Blueprint Lite → Discovery → Growth Sprint → Growth Blueprint → Campaign World`

## Capture surfaces

The following should all converge on the same contract:

- Narratiive website Growth Diagnostic
- Tally form
- LinkedIn lead capture
- referrals
- events / QR codes
- cold outreach replies
- future inbound forms

## Tony ingestion contract

Authenticated POST to the existing Tony live bridge:

`http://127.0.0.1:8790/leads/ingest`

Authorization:

`Bearer <TONY_BRIDGE_TOKEN>`

Tony accepts either:

1. the normalized lead object; or
2. the complete JSON output from the Notion Create Page step.

The second form is preferred in n8n because it removes field-by-field mapping. After the Notion node succeeds, add one HTTP Request node which POSTs the complete current item to `/leads/ingest`. Tony extracts the Notion page ID, Contact, Company, Email, Source, Status, Notes, timestamps and URL himself.

For inbound `Tally`, `Growth Diagnostic` and `Website` records, Tony supplies missing workflow defaults without marking the lead qualified:

- `Status` -> `New` when absent
- `Lead Temperature` -> `Warm` when absent
- `Pipeline Stage` -> `New Diagnostic` when absent
- `Recommended Next Action` -> confirm the diagnostic input package, research verified public evidence, route Blueprint Lite drafting to Claude, preserve evidence lineage, and move the exact artefact to human review
- `AI Summary` -> factual summary derived from submitted Notes when absent

Explicit later commercial judgement always wins. Tony never overwrites a supplied `Hot`, `Discovery Call`, proposal stage, or other explicit decision.

## Website

The Narratiive website Growth Diagnostic must POST its completed lead package to the production diagnostic webhook after local submission persistence. The webhook is the bridge into the canonical commercial system; a local website database row alone is not a completed lead handoff.

Website records retain `Source = Growth Diagnostic`. The immediate browser result is the Growth Diagnostic result. Blueprint Lite is a separate personalised follow-up and must not be described as sent until the downstream workflow has decision-grade delivery evidence.

The website must be safe to retry. Replaying the same logical submission must not create duplicate canonical leads, duplicate Blueprint Lite generation jobs, or duplicate sends.

## Tally

Published form: `Information and Insight` (`ob5yYe`).

Current production webhook:

`https://lushly-spoof-reheat.ngrok-free.dev/webhook/diagnostic-lead`

The tested production path is:

```text
Tally / Website
  -> ngrok
  -> n8n /webhook/diagnostic-lead
  -> Leads — CANONICAL
  -> Tony /leads/ingest
```

Tally only needs to provide captured facts such as name, company, email and growth challenge. Narratiive enrichment fields are completed after capture.

Do not invent a qualified stage merely because a Tally or Growth Diagnostic form was completed. Qualification is a later commercial judgement.

## Blueprint Lite handoff

After Tony confirms a completed Growth Diagnostic lead:

1. Tony preserves the exact prospect input package and stored diagnostic result.
2. Tony routes authorised research and drafting to Claude under `products/blueprint-lite/README.md`.
3. Claude returns a versioned Blueprint Lite with evidence lineage.
4. Tony validates the required structure and moves it to `Awaiting Review`.
5. Human approval is recorded for the exact artefact version.
6. Only then may the approved external tools store/send the recipient-facing artefact.
7. Tony records execution evidence before moving the prospect to `Sent` / Discovery.

## Notifications

Gmail notification is optional convenience, not a source-of-truth or business-continuity dependency. A lead path is healthy when the record is stored and Tony knows about it. Email can be enabled or disabled independently without changing lead state.

## Executive behaviour

Tony must distinguish:

1. new inbound leads,
2. Blueprint Lite research/review/delivery,
3. Discovery conversations,
4. Growth Sprint proposals / active commercial work,
5. won/lost business and commissioned Growth Blueprints.

Tony explicitly answers `/leads`, `inbound leads`, `today's leads`, `yesterday's inbound leads`, and equivalent plain-language commercial queries from the live lead store. If the live lead feed is unavailable, Tony must say so. He must not infer `zero leads` from missing data.

## Acceptance test

A production Growth Diagnostic path passes only when all of the following are true:

1. Submit a new labelled website diagnostic lead.
2. A record appears in `Leads — CANONICAL` once and only once.
3. The record has `Source = Growth Diagnostic` and the captured facts.
4. n8n POSTs the complete Notion Create Page output to `/leads/ingest`.
5. Tony can immediately show the new lead plus the Blueprint Lite next action.
6. The Blueprint Lite task is routed to Claude and returns a versioned artefact with evidence lineage.
7. Tony moves that artefact to human review and does not send it before approval.
8. Approved delivery records execution evidence and advances the prospect to Discovery.
9. Replaying the same website/n8n/Notion result does not create a duplicate canonical lead, Tony lead, artefact, or send.
10. A failed downstream webhook leaves the website lead safely persisted and retryable without falsely claiming that Blueprint Lite was delivered.
