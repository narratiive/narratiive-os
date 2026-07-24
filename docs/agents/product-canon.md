# Narratiive OS Product Canon

Status: Governance index to existing canon

This document locates and protects existing product truth. It does not replace
the canonical files it references.

## Canonical names

| Name | Meaning |
| --- | --- |
| `Narratiive OS` | The repository and operating system |
| `Growth Specification` | The canonical parent object for the strategy-to-performance lifecycle |
| `Narratiive Growth Blueprint` / `Growth Blueprint` | The premium strategic product and its working short name |
| `Campaign World` | The campaign-territory artefact downstream of the Growth Blueprint |
| `Creative Director's Bible` | The creative-direction artefact downstream of Campaign World |
| `Production Pack` | The asset-level production contract downstream of approved creative direction |
| `Asset Manifest` | The machine-readable register of asset identity, state, lineage, and delivery |
| `Performance Feedback` | The governed performance-learning object downstream of delivered assets |
| `Narratiive Signal` | The external outreach product |
| `Opportunity Card Pipeline` | The internal workflow name for Narratiive Signal |

Do not use `Opportunity Card` as the external product name. Do not rename a
specialist or collapse the Growth Specification, Growth Blueprint, Campaign
World, Creative Director's Bible, Production Pack, Asset Manifest, or
Performance Feedback into one generic “strategy deck.”

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

## Narratiive Growth Blueprint

The active production bundle is resolved through
`knowledge/blueprint/manifest.json`. Its approved, checksum-locked components
are:

- `population-system.md`
- `blueprint-schema-v3.md`
- `visual-framework-library-v1.md`
- `visual-intelligence-system-v1.md`

The Blueprint is a premium strategic product, not merely a presentation. It
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

## Narratiive Signal

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
