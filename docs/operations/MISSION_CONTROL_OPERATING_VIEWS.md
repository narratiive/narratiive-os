# Mission Control operating views

Status: branch implementation; production acceptance outstanding.
Owner: Worker Infrastructure. Commercial/Delivery review is required for the
proposed marketing direction; no product canon or specialist prompts change.

## Existing service and authority

The same loopback-only `GET /mission-control` and `/mission-control/api` routes
serve three views. No additional daemon, database or CRM is introduced. Notion
continues to own commercial fields. Persisted workflow snapshots, scoped event
journals, immutable outputs and exact-version approval records own execution
truth. This distinction is already established in REAL_EVIDENCE_PILOT.md.

The UI reads current Notion leads without updating the synchronised lead cache.
Explicit `TONY_INBOUND_LEAD_SOURCE=local_projection` retains the existing local
mode. Failed authoritative reads return 503 and the UI marks state unavailable;
there is no silent empty/successful fallback. Existing executive suppression
continues to apply, including synthetic, archived and completed/no-action leads.
Historical suppressed records must be inspected through the existing direct
Tony/runtime lookup, not mistaken for deleted records.

## Business Pipeline

A business detail includes all readable scoped workflow events, step owners,
retry/attempt counts, quality records, artefact links, next action, last recorded
successful activity and explicit evidence gaps. The timestamp is historical
execution evidence, not a live heartbeat. Missing profile/analysis/outputs remain
unrecorded, rather than being invented from a pipeline label.

Earlier stages are `unknown` until their workflow evidence verifies completion;
reaching Delivery alone no longer ticks earlier stages complete. A verified run
requires completed stages, locally readable tenant-scoped outputs matching their
checksums, matching stage-completed events, passed persisted quality results,
and exact current output approval history plus matching `approval.granted`
evidence when the run requires approval. Legacy incomplete evidence remains
inspectable and is labelled unverified; no record is migrated or repaired.
The read projection does not confer release authority or commercial readiness.

## Operations Centre

Existing connection evidence is retained. Runs, owners, attempts, retries and
open blockers come from the same visible workflows. Both stalled and unverified
completion states enter Attention. No Tony online claim is inferred from the
page loading or an old workflow event.

If the established `TONY_DISPATCH_N8N_MODE=local_sqlite` adapter is configured,
the existing `TONY_N8N_DATABASE_PATH` is opened in SQLite read-only mode. Only the
newest 50 retained execution metadata rows are read: execution/workflow IDs,
recorded status, start/stop and retry lineage. No credentials, node payloads or
execution bodies are queried. Unsupported schemas are degraded. No database is
created if its configured path is missing. This is a bounded operational view,
not complete ingestion certification. Some existing workflows deliberately do
not retain payloads; do not enable payload retention to fill this view.

## Marketing Studio

The proposed North Star and editorial priorities are labelled for Matt's review.
No publishing capability is added. The view must not be described as a working
Claude production integration until its real authoritative source is connected.

An optional `NARRATIIVE_NOTION_MARKETING_DATA_SOURCE_ID` selects the **existing,
active** marketing collection. It reuses the established runtime Notion token,
API version and bounded read transport. Confirm its ownership/schema before
configuration. The discovered archived Content OS source is explicitly rejected
as active production; this change does not create or revive a collection.

Required property names: `Title`, `Status`. Optional: `Concept`, `LinkedIn Copy`,
`Commercial Objective`, `Owner`, `Blocker`. Last edit time comes from Notion.
The bound is 200 rows; overflow/incomplete pagination fails closed rather than
presenting a complete-looking partial queue. Field mapping failures are visible.
Approval and publication remain unverified without exact-version approval and
publication receipts. Performance/revenue attribution is unavailable until
real metrics and attribution evidence are connected; absent metrics are not 0.

## Compatibility and active work

Base: main commit `412bbfd470bd233fc48697dc7d995392d384df44`.
Branch: `feat/mission-control-operating-views`.
Open PRs #487, #492 and #493 carry a separate stack for briefing, naming and inbound
classification. This branch does not modify their prompts, contracts, inbound
normalisation or workflow definitions. The only live-bridge interface changes
are fresh read-only leads and the two injected read loaders. Reconcile those
small composition changes when integrating the stack; do not cherry-pick its
inbound repair here. Existing canonical names are retained until that stack's
versioned presentation layer is integrated.

## Production acceptance still required

After independent review, green CI and Matt's deployment approval:

1. Resolve the exact three test entity/workflow identities from the Mac's
   canonical stores, retaining synthetic labels and executive suppression.
2. Open the existing local Mission Control on the Mac Mini. Select an eligible
   business and compare every stage/event/artefact with Tony's direct status.
3. Check a blocked run, a completed run, a retry and a missing output. Repeated
   GETs must not change workflow/event/artefact/lead stores.
4. Verify the actual n8n database schema and execution metadata, including a
   failed execution and its retry. Do not treat missing retention as success.
5. Confirm the active marketing collection, validate the property mapping and
   inspect a real draft, approval record, publication receipt and commercial
   metric where available. Keep missing evidence explicit.
6. Inspect desktop/mobile layouts on the Mac, freshness/unavailable feedback,
   detail modal, keyboard navigation and artefact access. UI syntax/structure
   checks are not visual acceptance.

Do not deploy this branch, mutate historical business records, send outreach or
expand publishing as part of these development changes.
