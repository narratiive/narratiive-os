# Start here — Narratiive OS

Narratiive is an evidence-led strategic and creative agency. Narratiive OS turns
approved evidence into commercial strategy, creative direction and finished
assets through specialist work, traceable handoffs, quality review and human approval.

## Current commercial products

| Product | Commercial purpose |
| --- | --- |
| **Groundwork** | Lead intelligence, qualification, business/market research and Discovery preparation. |
| **Fieldwork** | “Seven days to find a clearer way to grow.” Evidence-led strategy after agreed prerequisites: find the growth audience, build the advantage, show the way to growth; executive presentation with research, source and financial appendices. |
| **Sketchbook** | The creative world derived from approved Fieldwork: territories, distinctive assets, typography, imagery, copy, motion, storytelling and campaign concepts. |
| **Launchpad** | Creative production, asset QA, delivery preparation and approved activation; publication and spend remain separately gated. |

**Blueprint Lite and Growth Sprint are retired client-facing names.** Their
presence in old documents, paths or workflow IDs does not approve their use in
new proposals or communications. Growth Blueprint, Campaign World and Creative
Director's Bible are internal artefact contracts, not additional commercial offers.
Read [product canon](docs/agents/product-canon.md) for the precise distinctions.

## Repository, people and architecture

Canonical repository: [narratiive/narratiive-os](https://github.com/narratiive/narratiive-os).
Canonical local runtime checkout: `/Users/admin/Documents/narratiive-os`.
Use isolated branches/worktrees for engineering; deploy only from the canonical checkout.

Matt owns company/product decisions and exact-version client-facing approval.
Tony is the COO: he commissions and coordinates specialists, tracks canonical
state, routes corrections and approvals, and communicates useful progress and
next actions. He does not replace specialists or approve their work for Matt.
The Constitution defines the remaining roles and decision rights.

The existing specialist chain is Research Analyst → Strategy Director → Campaign
World Generator → Creative Director → Quality Reviewer. Within strategy,
Research → Strategic Synthesis → Strategy Thesis → Growth Blueprint remains the
internal evidence-to-strategy sequence. Growth Specification is the parent object;
Growth Blueprint, Campaign World, Creative Director's Bible, Production Pack,
Asset Manifest and Performance Feedback remain distinct, versioned objects.

`runtime/` holds workflow state, queues, providers, approvals and projections;
`workflows/` and `agents/` hold execution/specialist contracts; `knowledge/`,
`templates/` and `schemas/` hold product/artefact contracts; `openclaw/` exposes
authenticated interfaces; `tests/` verifies them. Read the relevant implementation
and configured capabilities before claiming an integration works. Mission Control
is a view of canonical state, not another source of business truth.

## Current acceptance goal — not a completion claim

The Origin fictional rehearsal must progress from the approved proposal through
internal bodies of work and clearly labelled simulated gates to **two finished
branded campaign stills**, with headlines and calls to action, real review files,
and Tony's verified folder confirmation. The stills await Matt's final review.
No video, real Origin contact, payment or publication is authorised by that goal.
The rehearsal was paused at Matt's request on 5 November 2026. Inspect current
state and obtain an explicit resume instruction before executing it; this page
is context, not permission to run a journey.

## Before coding

Read this file, [AGENTS.md](AGENTS.md) and its required governance documents.
Inspect Git status, branch/history and **active pull requests** (including their
changed files) before editing. Coordinate overlap; an open PR is not merged truth.
Use the checked-out implementation and current evidence rather than old chats.

Work on a branch, make the smallest coherent change, run proportionate checks,
record independent review against the exact commit, and satisfy merge governance.
Preserve historical IDs, specialist names, immutable artefacts, append-only history,
workspace isolation and backward compatibility. Never bulk-rename historical records.
Quality or generation success is not human release approval. Keep documentation
work separate from runtime changes; deploy only when the actual change requires it.
