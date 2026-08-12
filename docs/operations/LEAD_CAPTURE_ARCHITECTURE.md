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
- `Recommended Next Action` -> review fit and decide between Opportunity Card / discovery
- `AI Summary` -> factual summary derived from submitted Notes when absent

Explicit later commercial judgement always wins. Tony never overwrites a supplied `Hot`, `Discovery Call`, proposal stage, or other explicit decision.

## Website

The existing website flow already creates records in `Leads — CANONICAL`. Preserve it. The only required Tony handoff is the final HTTP Request after successful Notion creation.

Website records should retain their existing source classification (for example `Growth Diagnostic`).

## Tally

Published form: `Information and Insight` (`ob5yYe`).

Current production webhook:

`https://lushly-spoof-reheat.ngrok-free.dev/webhook/diagnostic-lead`

The tested production path is:

```text
Tally
  -> ngrok
  -> n8n /webhook/diagnostic-lead
  -> Leads — CANONICAL
```

Tally only needs to provide captured facts such as name, company, email and growth challenge. Narratiive enrichment fields are completed after capture.

Do not invent a qualified stage merely because a Tally form was completed. Qualification is a later commercial judgement.

## Notifications

Gmail notification is optional convenience, not a source-of-truth or business-continuity dependency. A lead path is healthy when the record is stored and Tony knows about it. Email can be enabled or disabled independently without changing lead state.

## Executive behaviour

Tony must distinguish:

1. new inbound leads,
2. qualified opportunities,
3. proposals / active commercial work,
4. won/lost business.

Tony explicitly answers `/leads`, `inbound leads`, `today's leads`, `yesterday's inbound leads`, and equivalent plain-language commercial queries from the live lead store. If the live lead feed is unavailable, Tony must say so. He must not infer `zero leads` from missing data.

## Acceptance test

A production lead path passes only when all of the following are true:

1. Submit a new website or Tally lead.
2. A record appears in `Leads — CANONICAL`.
3. The record has the correct `Source` and captured facts.
4. n8n POSTs the complete Notion Create Page output to `/leads/ingest`.
5. Tony can immediately answer `inbound leads` and show the new lead plus next action.
6. Tony's next `/morning` or `/evening` brief shows the new lead.
7. Replaying the same Notion result does not create a duplicate Tony lead.
