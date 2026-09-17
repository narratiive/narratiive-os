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

1. No first-class runtime identity currently binds Client, Brand, Market,
   Product and Campaign before downstream creative work begins.
2. The registered Growth Blueprint to Campaign World handoff produces one
   Campaign World; it does not model several candidate worlds and a bound human
   selection.
3. Tony's taste judgement is not represented separately from independent
   quality review and Matt's approval.
4. Campaign World and Creative Director's Bible lifecycle state is not yet
   exposed as one durable multi-client campaign portfolio.
5. Channel specifications and Production Pack jobs are specified but are not
   yet generated and routed through operational production adapters.
6. Asset Manifest rules are canonical documentation rather than the complete
   executable asset-version and review service.
7. Deployment, performance ingestion and learning/iteration are not yet live
   campaign adapters.

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
2. **Tony control surface** — the authenticated read surface now exposes the
   multi-client Campaign Engine portfolio, current stage, next action and human
   gate through deterministic commands and Tony's native state-read tool.
   Candidate comparison is now included in campaign detail as an exact-version
   selection brief: quality verdict, Tony disposition, rationale, checksum and
   readiness are visible while automatic selection remains forbidden. Exact
   approval operations and explicit Notion projections remain the next
   control-surface work.
3. **Campaign World generation** — reconcile the existing Campaign World agent
   and template with multiple candidate generation, a quality rubric and Tony's
   bounded taste review. Prove the flow from one approved Growth Blueprint.
4. **Creative Director's Bible** — reconcile the v2 draft specification with
   the stable template, persist one approved Bible, and prove version-bound
   review and revision. The runtime now binds every submitted Bible version to
   the exact selected Campaign World ID, version and checksum; revision clears
   stale reviews rather than carrying them onto new creative work.
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
   delivery, publication or media-spend authority.
6. **Production orchestration** — route jobs by declared capability, ingest
   generated files into Drive, register versions and validate technical
   specifications. The exact-version human asset-approval stop is implemented;
   provider routing and technical-file validation remain bounded follow-on work.
7. **Delivery and deployment preparation** — assemble the approved client asset
   suite. Add Meta, TikTok and Google adapters only after exact action-preview,
   approval, idempotency and reconciliation contracts are proven. No adapter
   may commit spend or publish autonomously.
8. **Performance and iteration** — normalise platform metrics against campaign,
   channel and asset IDs; produce evidence-graded findings and human-approved
   recommendations; create a new downstream version rather than mutating the
   approved creative source.

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
