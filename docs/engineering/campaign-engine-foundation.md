# Narratiive Campaign Engine foundation

Status: first bounded implementation slice

## Current-state architecture

The existing production system already supplies the control plane needed for a
Campaign Engine:

```text
n8n / Telegram / future interfaces
  -> authenticated Tony/OpenClaw bridge
  -> Narratiive OS public command and workflow boundary
  -> workspace-scoped runs, events, artefacts, approvals and execution evidence
  -> approved operational projection to Notion
  -> approved deliverables and asset files in Google Drive
```

The inbound and strategy journey is implemented through durable workflows from
Growth Diagnostic to Blueprint Lite, Discovery, Growth Sprint, Research and
Growth Blueprint. The production workflow registry already declares the later
handoffs from Growth Blueprint to Campaign World, Creative Director's Bible,
asset production, delivery and follow-up. The Growth Specification, Production
Pack, Asset Manifest and Performance Feedback specifications define the intended
strategy-to-learning chain.

The later campaign stages are not yet equivalent to the live inbound journey.
Most are registered contracts or canonical specifications rather than a fully
composed, provider-backed and production-accepted runtime. The existing
Production OS acceptance test currently proves the internal chain through an
approved Growth Blueprint, not through a delivered asset suite.

## Components to reuse

- workspace and client isolation;
- the generic workflow engine, coordinator, retries and restart recovery;
- immutable artefact catalogue and parent/source lineage;
- approval tokens bound to exact artefact checksums;
- Quality Reviewer and revision routing contracts;
- Tony's durable commitment, proactive return and Mission Control surfaces;
- the authenticated OpenClaw, Telegram and n8n boundary;
- read/write classification and consequential-action preview;
- Notion, Gmail and Drive adapters with verified execution receipts;
- Growth Object validation and campaign progress projection;
- Campaign World, Creative Director's Bible, Production Pack, Asset Manifest
  and Performance Feedback canon.

No advertising API is required for the foundation.

## Gaps against the Campaign Engine

1. The canonical Campaign Engine and every registered downstream workflow now
   require one stable identity binding Client, Brand, Market, Product and
   Campaign before Campaign World work begins. Automated creation and Notion
   reconciliation of that identity from approved onboarding remain outstanding.
2. The canonical Campaign Engine models several Campaign World candidates, and
   the registered Growth Blueprint workflow now generates exactly three,
   quality-checks each, records Tony's bounded taste disposition and requires
   Matt to select one exact candidate checksum. Live-provider acceptance and
   Matt's taste-calibration examples remain outstanding.
3. Tony's taste judgement is now represented separately from independent
   structural quality review and Matt's selection; it is deliberately a bounded
   triage rubric rather than autonomous strategy or approval.
4. Campaign World and Creative Director's Bible lifecycle state is not yet
   exposed as one durable multi-client campaign portfolio.
5. The registered workflow now generates channel specifications, Production
   Pack jobs and a planned Asset Manifest from the exact approved Bible. Live
   creative-tool adapters remain unconfigured, so provider execution correctly
   blocks after its separate human approval gate.
6. Asset versions, review approval, delivery packaging and receipt-backed
   client delivery now have executable contracts. Live Drive ingestion/probing
   and a configured client-delivery provider remain outstanding.
7. Meta, TikTok and Google performance ingestion is read-only and normalized.
   Normalized snapshots and Tony's bounded recommendations can now be converted
   into immutable Performance Evidence, Campaign Insight and pending Creative
   Iteration records. Notion projection and live multi-client scheduling of
   that learning cycle remain outstanding; platform mutation remains disabled.

## Data model and state machine

The first implementation uses the existing canonical term `Campaign World`.
Several Campaign World candidates provide the requested creative-world choice;
one becomes the approved canonical Campaign World.

```text
CampaignIdentity
  workspace_id
  client_id
  brand_id
  market_ids[]
  product_ids[]
  campaign_id

Approved Growth Blueprint
  -> multiple versioned Campaign World candidates
  -> independent Quality Reviewer verdict per candidate
  -> Tony forward/return taste disposition per candidate
  -> Matt selects one exact candidate checksum/version
  -> versioned Creative Director's Bible
  -> independent Quality Reviewer verdict
  -> Tony forward/return taste disposition
  -> Matt approves the exact Bible checksum/version
  -> Production Planning
```

Tony may return work below the Narratiive bar, and may recommend a quality-passed
option, but cannot approve it or silently rewrite specialist work. A candidate
cannot reach Matt unless it passes independent quality review and Tony forwards
it. Growth Blueprint approval, Campaign World selection and Creative Director's
Bible approval are explicitly bound to Matt; a Tony-authored approval is rejected.
Approval is invalid when the artefact ID, version or checksum changes. Matt's
Campaign World selection now has an application-service operation that persists
the exact approved candidate through the compare-and-swap boundary.

Campaign state is append-only, hash-chained, idempotent, workspace-scoped and
safe under concurrent updates. Persisted stage transitions now use an atomic
compare-and-swap boundary: stale callers, illegal stage skips, identity changes
and attempts to replace approved Blueprint evidence fail closed. The portfolio
projection prioritises campaigns waiting on Matt while retaining the next action
for every active campaign.

The Campaign Engine preparation state cannot authorise publication or media
spend. Those authorities remain false by construction. Future deployment
adapters must prepare an exact action preview and obtain a separate human
approval before any publication or spend mutation.

## Operational source-of-truth boundary

Notion remains the human-facing operational source of truth for clients,
campaign ownership, gates, status and next actions. Google Drive remains the
file repository for approved deliverables and asset versions. n8n remains an
action and integration layer.

Narratiive OS remains authoritative for execution truth: workflow transitions,
immutable artefact versions, evidence lineage, approvals, retries, idempotency
and provider receipts. Notion updates must therefore be explicit projections
through the public gateway with verified receipts. Notion is not allowed to
silently overwrite execution history, and runtime state is not allowed to claim
that Notion changed without execution evidence.

## Implementation sequence

1. **Campaign foundation** — implement and verify campaign identity, state
   transitions, exact-version gates, append-only persistence and multi-client
   portfolio projection. This slice is now implemented in
   `runtime/campaign_engine.py`. Campaign bootstrap now requires and persists
   Matt's approval bound to the exact Growth Blueprint ID, version and checksum;
   retries are idempotent and conflicting campaign reuse fails closed.
   The registered Campaign World, Creative Bible, asset-production, delivery
   and follow-up workflows now carry and validate the same canonical identity;
   missing, partial or duplicate market/product identifiers fail before worker
   dispatch.
2. **Tony control surface** — the authenticated read surface now exposes the
   multi-client Campaign Engine portfolio, current stage, next action and human
   gate through deterministic commands and Tony's native state-read tool.
   Candidate comparison is now included in campaign detail as an exact-version
   selection brief: quality verdict, Tony disposition, rationale, checksum and
   readiness are visible while automatic selection remains forbidden. Exact
   approval operations and explicit Notion projections remain the next
   control-surface work.
3. **Campaign World generation** — the registered workflow now requests exactly
   three materially distinct candidates from one approved Growth Blueprint,
   validates every candidate, routes them through Tony's deterministic taste
   triage, pauses for human approval, and records Matt's exact ID/checksum
   selection before Creative Bible handoff. The selection cannot produce,
   publish, deliver or fund an asset. Live Claude acceptance and iterative taste
   calibration against Matt's decisions remain follow-on work.
4. **Creative Director's Bible** — the operational workflow now generates the
   structured v2 Bible, applies the complete structural contract, routes it
   through Tony's separate bounded taste/producibility review, and pauses for
   Matt. Matt's approval is bound to the exact Bible checksum and is required
   before asset-production handoff; Tony, stale versions and unreviewed Bibles
   fail closed. Production, publication and media-spend authority remain false.
   Live-provider acceptance and calibration against Matt's review history remain
   follow-on work.
5. **Production planning** — the state machine now accepts versioned channel
   specifications and capability-routed Production Pack jobs only when every
   record traces to the exact approved Bible. Jobs require human review, the
   Production Pack requires Matt's exact-version approval, and neither the plan
   nor its jobs can authorise publication or media spend. An approved Production
   Pack can now create a planned Asset Manifest with immutable asset IDs, initial
   version numbers and exact job, specification, Bible and Production Pack
   lineage. Planned records cannot claim files, approval, delivery, publication
   or spend. Generated files can now be registered only as append-only versions
   in Drive, with checksums and exact Asset Manifest/job lineage. Version numbers
   cannot be overwritten or skipped, every generated version requires human
   review, and generation cannot imply approval, delivery or publication. A
   complete suite now enters an explicit review cycle containing the latest exact
   version of every planned asset. Matt's review is checksum-bound per file;
   Tony cannot substitute for that approval. Changes requested return the
   campaign to asset production without erasing the prior review cycle, while
   unanimous approval advances to an approved asset suite that still carries no
   delivery, publication or media-spend authority. The generic workflow now
   exposes `/assets` and `/approve-assets`; the latter records Matt's identity,
   the exact suite checksum and every approved asset-version ID before delivery
   preparation can begin. Stale, incomplete and Tony-authored approvals fail
   closed.
6. **Production orchestration** — the operational workflow now separates local
   production planning from provider execution. It derives one versioned channel
   specification, human-reviewed job and planned Asset Manifest record for every
   Creative Bible asset-matrix entry. The exact Production Pack pauses for human
   approval; provider execution is a second external-write stage with another
   approval boundary. With no configured creative provider, it fails closed
   rather than claiming output. Route jobs by declared capability, ingest
   generated files into Drive, register versions and validate technical
   specifications. A Drive file-probe receipt can now create an append-only
   technical validation bound to the exact asset checksum and channel
   specification. File existence/readability, type, dimensions, aspect ratio,
   duration, checksum and Production Pack lineage are critical checks; a missing
   or failed latest validation blocks the human review gate. The exact-version
   human asset-approval stop is implemented. Each Production Pack job can now be
   deterministically matched to one available worker through its declared
   capability and selection policy. The planned route records the worker,
   provider, policy, reason and exact Production Pack checksum without invoking
   the provider or claiming that output exists; unavailable capabilities fail
   closed. Before a provider can be invoked, the engine now prepares a canonical
   dispatch payload containing the exact workspace, client, campaign, Pack,
   route, job, channel specification, planned asset and production parameters.
   Matt must approve that payload's checksum; Tony and stale approvals are
   rejected, and no preview can authorise execution, publication or spend.
   A configured creative provider can now execute only after both Production
   Pack and external-write approval. Its result must cover every exact planned
   asset/job pair, bind each generated version to the Asset Manifest checksum,
   supply a receipt for every version, and explicitly deny delivery,
   publication and spend. Missing providers and malformed, partial, stale or
   over-authorised provider results fail closed. Live provider credentials,
   Drive ingestion and live probe execution remain bounded follow-on work.
7. **Delivery and deployment preparation** — the exact Matt-approved asset
   suite is now assembled locally into a deterministic client package and
   manifest. Every entry preserves its asset-version ID, file checksum, Drive
   URI, production job, Asset Manifest and approved-suite lineage. Preparation
   creates only a checksum-bound action preview with an idempotency key; it
   cannot send anything. Client delivery is a separate external-write stage and
   therefore pauses for another explicit human approval. A configured delivery
   provider must return receipt-backed evidence covering every exact version;
   partial, stale or over-authorised results fail closed. With no provider, the
   workflow stops safely after package approval. Delivery never grants ad
   publication or media-spend authority. Add Meta, TikTok and Google adapters
   only after equivalent exact action-preview, approval, idempotency and
   reconciliation contracts are proven.
8. **Performance and iteration** — after receipt-backed delivery, the terminal
   workflow now creates a bounded measurement and follow-up plan tied to the
   canonical campaign and exact delivered asset-version IDs. It requires
   verified tracking and provider mappings, routes Meta, TikTok and Google into
   read-only normalised ingestion, and specifies evidence-graded insights plus a
   human-approved creative iteration brief. Tony's role is explicitly
   `orchestrate_monitor_and_quality_check`; strategy authority remains human and
   neither publication nor spend can be authorised. The existing Media Control
   Layer already supplies read-only cross-platform snapshots and deterministic
   recommendations. The Campaign Learning service now binds those snapshots to
   approved Narratiive asset-version IDs and persists immutable Performance,
   Insight and pending Creative Iteration records. Unapproved mappings,
   cross-campaign evidence and non-advisory recommendations fail closed. Each
   learning cycle explicitly requires Notion projection. A dedicated projection
   service now prepares the exact operational summary and performs an
   idempotent Notion write only with Matt's authenticated approval; mismatched
   record, projection-key or cycle-checksum evidence requires reconciliation.
   Wiring that service into Tony's live multi-client scheduler remains
   follow-on work.

Each slice must extend the live acceptance run from its last verified checkpoint
and must prove restart, retry, isolation, lineage and approval behaviour before
the next slice begins.

## Risks and architectural conflicts

- **Dual truth:** Notion and Narratiive OS will diverge if updates bypass the
  public gateway or verified projection receipt.
- **Canon reconciliation:** the Creative Director's Bible v2 remains labelled a
  draft system specification, while a stable Markdown template and older
  five-stage workflow remain active. This requires a deliberate product review,
  not an inferred promotion.
- **Campaign terminology:** the repository canon uses Campaign World. Adding a
  separate canonical Creative World object would create competing lifecycle
  terms, so candidate creative worlds are modelled as Campaign World candidates.
- **Tony authority:** Tony can reject work below the internal bar and recommend
  what deserves Matt's attention, but cannot become the strategist, specialist,
  Quality Reviewer or human approver.
- **Taste calibration:** Tony's taste disposition needs an explicit rubric and
  examples derived from Matt's decisions. It must remain traceable and must not
  be presented as objective quality.
- **Production-provider claims:** documented references to creative tools do not
  prove a configured operational adapter. Missing capabilities must fail closed.
- **Asset identity:** Drive filenames and folders cannot substitute for stable
  Asset Manifest IDs, version lineage and checksums.
- **External consequences:** publication, media spend, client delivery and
  authoritative external writes require separate exact-payload human approval
  and verified execution evidence.
