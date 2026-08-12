# Narratiive Lead Capture Architecture

## Decision

There is one commercial source of truth for prospects:

- Notion database: `Leads — CANONICAL`
- Database ID: `34b0c9cf-a8f2-80aa-9862-f05f4a65c676`
- Data source ID: `34b0c9cf-a8f2-80af-98e4-000b95243de6`

The older Leads database is legacy and must not receive new records.

## Principle

Every lead surface uses the same two-write contract:

```text
Capture surface
  -> n8n normalization
  -> Notion Leads — CANONICAL (source of truth)
  -> Tony POST /leads/ingest (synchronized executive state)
```

Notion owns the durable CRM record. Tony owns the live executive projection. A lead is not required to be qualified before Tony can see it.

## Capture surfaces

The following should all converge on the same contract:

- Narratiive website Growth Diagnostic
- Tally form
- LinkedIn lead capture
- referrals
- events / QR codes
- cold outreach replies
- future inbound forms

## Normalized Tony ingestion contract

Authenticated POST to the existing Tony live bridge:

`/leads/ingest`

Authorization:

`Bearer <TONY_BRIDGE_TOKEN>`

Payload:

```json
{
  "lead_id": "<Notion page id or stable lead id>",
  "contact": "Jane Smith",
  "company": "Example Ltd",
  "email": "jane@example.com",
  "source": "Tally",
  "status": "New",
  "pipeline_stage": "",
  "lead_temperature": "Warm",
  "recommended_next_action": "Review submission and decide the next commercial action.",
  "created_at": "2026-08-12T18:00:00Z",
  "notion_url": "https://www.notion.so/..."
}
```

Use the canonical Notion page ID as `lead_id` after the Notion create step. This makes retries idempotent: Tony upserts the same lead instead of duplicating it.

## Website mapping

The existing website flow already creates records in `Leads — CANONICAL`. Preserve it. Add one final HTTP Request step after the successful Notion create step that POSTs the normalized record to Tony `/leads/ingest`.

Website records should retain their existing source classification (for example `Growth Diagnostic`).

## Tally mapping

Published form: `Information and Insight` (`ob5yYe`).

Map:

- First name + Last name -> `Contact`
- Company name -> `Company`
- Email -> `Email`
- Source -> `Tally`
- Status -> `New`
- Lead Temperature -> `Warm` unless an explicit qualification rule says otherwise
- Website + Company size + Biggest Growth Challenge + newsletter choice -> `Notes` and/or `AI Summary`
- Recommended Next Action -> `Review submission and decide whether to invite to discovery.`

Do not invent a qualified stage merely because a Tally form was completed. Qualification is a later commercial judgement.

## Tally webhook

The current Tally webhook points at an old ngrok route. Replace it with the production n8n webhook for the canonical lead-ingestion workflow. The n8n workflow must perform both writes above.

The Tally app connector available to ChatGPT can inspect and edit the form but does not expose Tally webhook/integration settings, so the webhook URL itself must be changed in Tally's Integrations UI.

## Executive behaviour

Tony must distinguish:

1. new inbound leads,
2. qualified opportunities,
3. proposals / active commercial work,
4. won/lost business.

If the live lead feed is unavailable, Tony must say so. He must not infer `zero leads` from missing data.

## Acceptance test

A production lead path passes only when all of the following are true:

1. Submit a new website or Tally lead.
2. A record appears in `Leads — CANONICAL`.
3. The record has the correct `Source`.
4. n8n POSTs the normalized lead to `/leads/ingest`.
5. Tony's next `/morning` or `/evening` brief shows the new lead and recommended action.
6. Replaying the same event does not create a duplicate Tony lead.
