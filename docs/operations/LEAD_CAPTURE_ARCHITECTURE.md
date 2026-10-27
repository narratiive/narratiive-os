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

The approved customer-facing service sequence is:

`Groundwork → Discovery → Fieldwork → Sketchbook → Launchpad`

Internal identifiers including Blueprint Lite, Growth Sprint, Growth Blueprint,
Campaign World and Activation remain compatible and historical records are not migrated.

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

The second form is preferred in n8n because it removes field-by-field mapping. After the Notion node succeeds, add one HTTP Request node which POSTs the complete current item plus the normalised capture facts to `/leads/ingest`. Tony extracts the Notion page ID, Contact, Company, Email, Source, Status, selected service, business challenge, timestamps and URL himself.

For inbound `Tally`, `Growth Diagnostic` and `Website` records, Tony supplies missing workflow defaults without marking the lead qualified:

- `Status` -> `New` when absent
- `Lead Temperature` -> `Warm` when absent
- `Pipeline Stage` -> `New Diagnostic` when absent
- `Recommended Next Action` -> follow the explicitly selected service. A missing or GROUNDWORK preference may use the existing Blueprint Lite preparation path. FIELDWORK, SKETCHBOOK or LAUNCHPAD requires founder review and must not automatically start paid research or client communication.
- `AI Summary` -> factual summary derived from submitted Notes when absent

Explicit later commercial judgement always wins. Tony never overwrites a supplied `Hot`, `Discovery Call`, proposal stage, or other explicit decision.

## Website

The Narratiive website Growth Diagnostic must POST its completed lead package to the production diagnostic webhook after local submission persistence. The webhook is the bridge into the canonical commercial system; a local website database row alone is not a completed lead handoff.

Website enquiry records retain `Source = Website`, the submitted service preference and the submitted business challenge. A separate completed Growth Diagnostic retains `Source = Growth Diagnostic`. Tony must not reinterpret an explicit FIELDWORK preference as a Growth Diagnostic or automatically start GROUNDWORK/Blueprint Lite preparation.

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

Every legitimate new commercial enquiry also triggers one founder Telegram alert from the event-driven Tony ingestion boundary. The alert records a durable delivery start before one at-most-once send attempt, requires Telegram's message acknowledgement to claim delivery, logs failure or uncertain outcome, and suppresses replay by the stable submission identity. It never contacts the prospect or starts paid research.

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

1. Submit a new labelled website enquiry with an explicit service preference.
2. A record appears in `Leads — CANONICAL` once and only once.
3. The record has `Source = Website`, the selected service and the captured business challenge.
4. n8n POSTs the complete Notion Create Page output plus normalised capture facts to `/leads/ingest`.
5. Tony can immediately show the new lead, selected service and appropriate next action.
6. Exactly one acknowledged founder Telegram alert is recorded; replay does not send a duplicate.
7. FIELDWORK and later service preferences stop for founder review and do not start GROUNDWORK/Blueprint Lite preparation.
8. A GROUNDWORK path retains the existing Claude, evidence-lineage and human-review controls.
9. Replaying the same website/n8n/Notion result does not create a duplicate canonical lead, Tony lead, artefact, or send.
10. A failed downstream webhook leaves the website lead safely persisted without falsely claiming alert or artefact delivery.
