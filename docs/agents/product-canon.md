# Narratiive OS Product Canon

Status: Current commercial naming canon, version 1.2.0 — 5 November 2026

Read [START_HERE.md](../../START_HERE.md) first. Matt's approved commercial names
are **Groundwork, Fieldwork, Sketchbook and Launchpad**. This naming decision
supersedes conflicting external-product labels in older repository documents;
it does not change their technical contracts or immutable history.

## Commercial products and internal names

| Commercial product | Purpose |
| --- | --- |
| Groundwork | Lead intelligence, qualification, business/market research and Discovery preparation. |
| Fieldwork | “Seven days to find a clearer way to grow.” Premium evidence-led strategy delivered within seven working days after agreed prerequisites/inputs: find the growth audience, build the advantage, show the way to growth. Executive presentation with appropriate research, source and financial appendices. |
| Sketchbook | Rich creative-world development from approved Fieldwork: territories, distinctive brand assets, typography, imagery, copywriting, motion, storytelling, formats and contextual campaign concepts. |
| Launchpad | Creative production, asset QA, delivery preparation and approved activation. Publication and spend retain independent gates. |

The commercial journey is **Groundwork → Discovery → Fieldwork → Sketchbook → Launchpad**.
This is a commercial description, not a migration or renaming of executable stages.

| Internal name | Meaning retained for compatibility |
| --- | --- |
| Narratiive OS | Repository and operating system. |
| Growth Diagnostic | Existing diagnostic result/entry mechanism, not a fifth commercial product. |
| Blueprint Lite | Historical inbound/pre-sales artefact and workflow label; retired as a client-facing product name. |
| Growth Sprint | Historical paid-engagement/workflow label; retired as a client-facing product name. |
| Growth Specification | Parent object for the strategy-to-performance lifecycle. |
| Narratiive Growth Blueprint / Growth Blueprint | Strategic artefact contract used within Fieldwork; not a separate current offer. |
| Campaign World | Creative-territory artefact used within Sketchbook. |
| Creative Director's Bible / Creative Bible | Creative-direction artefact used within Sketchbook. |
| Production Pack / Asset Manifest | Production contract and asset identity/state/lineage register used in Launchpad. |
| Performance Feedback | Governed downstream learning object. |
| Narratiive Signal / Opportunity Card Pipeline | Existing specialist outreach contract and its internal workflow label; not additional names for the four commercial products. |

Preserve those internal names, historical workflow IDs, file paths, schemas,
specialist names and existing compatibility behaviour. Do not bulk-rename source
or historical records. The existing internal Fieldwork strategy sequence remains
`Research → Strategic Synthesis → Strategy Thesis → Growth Blueprint`.
`knowledge/strategy-thesis/README.md` governs the internal thesis contract and
exact-version gate. Tony orchestrates; specialists own content; Matt retains
commercial and client-facing approval. Naming does not grant execution authority.

Do not use Blueprint Lite, Growth Sprint, Narratiive Shift or Opportunity Card
as current client-facing product names. Older product files below remain
technical/specialist references; their historical commercial descriptions do
not override this naming canon. This reconciliation does not change output
requirements, pricing, release gates or workflow behaviour.

## Growth Specification

`knowledge/growth-specification/README.md` is the canonical parent-object
specification. Its object model is:

`Growth Specification → Growth Blueprint → Campaign World → Creative Director's Bible → Production Pack → Asset Manifest → Performance Feedback`

The parent is a system-level source of truth, not a single client deliverable.
The child-object specifications define separate responsibilities:

- the Growth Blueprint defines what should create growth;
- Campaign World defines the campaign universe that expresses the strategy;
- the Creative Director's Bible defines how that world should look, feel, sound,
  and behave;
- Production Pack defines how approved assets will be made;
- Asset Manifest records which assets exist, where they are, and their governed
  state;
- Performance Feedback records what happened, what was learned, and what an
  authorised next iteration should change.

Every object uses the shared metadata and lifecycle contract in
`schemas/shared/growth-object.schema.json`. The lifecycle is `draft`,
`in_review`, `approved`, `active`, `superseded`, or `archived`; structural
completeness never substitutes for commercial, creative, or release approval.
Superseded versions and object lineage remain addressable.

The Growth Specification's coverage table currently records the Growth
Blueprint canonical-path mapping as requiring review, and the Creative
Director's Bible v2 source is labelled `draft_system_specification`. Do not
promote either state by inference. The older five-stage workflow and stable
Markdown templates remain repository contracts and require an approved,
versioned reconciliation where they differ from the newer child-object
specifications.

## Narratiive OS delivery chain

The canonical specialist order is:

1. Research Analyst
2. Strategy Director
3. Campaign World Generator
4. Creative Director
5. Quality Reviewer

The Orchestrator controls stage readiness and handoffs but creates no
deliverables. Missing evidence remains missing. Each producing specialist owns
its output, and Quality Reviewer routes revisions to the earliest responsible
owner.

The stable reusable templates are:

- `templates/Growth_Blueprint.md`
- `templates/Campaign_World.md`
- `templates/Creative_Directors_Bible.md`

Their headings, markers, YAML contracts, tables, order, and placeholders are
part of the contract.

## Historical Blueprint Lite compatibility contract

`products/blueprint-lite/README.md` retains the existing technical pre-sales
contract. Its historical name is not approved for new client-facing work.

Blueprint Lite is generated only after a completed Growth Diagnostic and combines the prospect's own inputs with selective outside-in research. It is deliberately concise and provisional. Its job is to create recognition, useful strategic tension and excitement about potential while preserving a clear curiosity gap for Discovery and paid Fieldwork.

It is not the instant diagnostic result, not Narratiive Signal, not a generic lead magnet, and not a shortened paid Growth Blueprint.

Tony orchestrates, stores, validates and routes. Claude researches, reasons and drafts where the approved workflow assigns it. Recipient-facing release requires human approval for the exact artefact version.

## Narratiive Growth Blueprint

The active production bundle is resolved through
`knowledge/blueprint/manifest.json`. Its approved, checksum-locked components
are:

- `population-system.md`
- `blueprint-schema-v3.md`
- `visual-framework-library-v1.md`
- `visual-intelligence-system-v1.md`

The Blueprint is the internal strategic artefact supporting Fieldwork, not merely a presentation or a separately named commercial offer. It
should be intelligent, commercial, evidence-based, visually communicable, and
founder-friendly. Every slide carries evidence, insight, interpretation, and
implication, and must answer “So what?”

The canonical master is exactly 30 slides across six acts:

1. The Case for Change
2. Market and Competitive Diagnosis
3. Audience and Demand Opportunity
4. Positioning and Narrative Answer
5. The Growth System
6. Implementation and Measurement

The five-slide Executive Summary and ten-slide Diagnostic Teaser are generated
from the master. They are not independent products.

Creative Direction in the Blueprint is a hook, not finished creative
development. The Blueprint may establish territories, emotional texture,
reference world, likely formats, and commercial job; it does not include full
campaign execution, production-ready scripts, final art direction, or finished
assets by default.

The founder-grade target is 9.5/10. That target does not authorise score
inflation or replace human review.

## Narratiive Signal specialist outreach contract

The canonical files in `products/narratiive-signal/` must be read in this order:

1. `01-product-spec.md`
2. `02-editorial-style-guide.md`
3. `03-generation-contract.md`
4. `04-quality-rubric.md`
5. `05-review-checklist.md`

A Narratiive Signal is an unsolicited strategic gift for a carefully selected
business. It is not a free strategy deck, audit, proposal, generic agency
credential, or disguised meeting request.

Version 1.1 defines five separate deliverables that must not be collapsed into
one recipient-facing document:

1. internal work record and evidence lineage;
2. short personalised outreach email;
3. recipient-facing Narratiive Signal;
4. internal creative production brief for two short moving-image concepts, or
   one moving-image concept and one still concept;
5. final quality score and review checklist.

Only the outreach email and Signal are automatically recipient-facing. Approved
creative previews may be included, but prompts, source notes, rejected ideas,
scoring, and workflow commentary remain internal.

The recipient-facing Signal has seven sections: Personal opening, What we
noticed, Why we think that, The white space, If this were ours..., What we'd be
careful about, and Invitation. It contains one central insight, no more than
three concise evidence points, one white-space opportunity, and one creative
direction.

The outreach email is preferably 100–150 words, with an absolute maximum of 180,
and fits within one normal laptop viewport. The Signal is preferably 500–800
words, with an absolute maximum of 900 excluding short source footnotes; it is
preferably one or two designed pages, uses a third page only when a visual
genuinely requires it, and takes under three minutes to read.

The voice is warm, observant, direct, editorial, commercially literate,
imaginative, and concise. The primary editorial objective is maximum curiosity,
not maximum information.

A Signal may enter human review only at 90/100 or higher, with no dimension
below eight and every mandatory gate passing. It may not be sent until the human
approval checklist is complete and the approval is recorded.

Tony orchestrates. Claude researches, reasons, and writes. Higgsfield renders
speculative creative. Tony stores, validates, versions, and routes the finished
work; Tony does not silently rewrite strategic content.

## Evidence and source rules

- Use supplied and authorised sources only, except where the applicable product
  contract explicitly authorises public research.
- Distinguish fact, source note, interpretation, assumption, and open question.
- Every material claim is supported or clearly qualified.
- Do not invent quotes, statistics, customer attitudes, proof points, competitor
  activity, precision, or familiarity.
- Retain internal source locations and evidence lineage even when source
  scaffolding is removed from the client-facing artefact.
- Public evidence is the default for a Narratiive Signal; private material
  requires explicit approval.

## Canon change control

A canon change is substantive. Authority and required reviewers are defined by
the product-canon decision class in `decision-authority.md`. The change also
requires a dedicated branch and pull request, a new version and changelog entry,
a checksum/manifest update where applicable, and regression review across
prompts, templates, agents, runtime validation, tests, examples, derivatives,
and client-facing outputs.

Never edit a checksum-locked component without updating its governed version and
manifest through the established import/version process.

## Naming reconciliation changelog

- **1.2.0 — 5 November 2026:** Matt explicitly instructed repository reconciliation
  to Groundwork, Fieldwork, Sketchbook and Launchpad. Retired Blueprint Lite and
  Growth Sprint as external names; retained technical contracts, stable IDs,
  specialist ownership and historical artefacts. Added the root contributor
  introduction. No checksum-locked Blueprint component or runtime rule changed.
