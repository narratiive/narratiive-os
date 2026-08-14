# Narratiive Knowledge

`knowledge/` is the canonical knowledge layer inside Narratiive OS.

There is one source of truth: `narratiive/narratiive-os`.

Reusable doctrine, frameworks, research rules, templates and strategic IP belong here. Runtime and workflow code remain elsewhere in the same repository. Notion remains the live operational state layer and Google Drive remains the client-facing deliverable layer.

## Structure

- `blueprint/` — locked canonical Growth Blueprint source assets.
- `doctrine/` — durable beliefs, vision and strategic context.
- `governance/` — rules for classifying and maintaining knowledge.
- `handbook/` — Narratiive-owned models, principles and public-facing IP.
- `research/` — source material and evidence where appropriate.
- `migrations/` — repository consolidation records and legacy mapping.

## Mandatory agent rule

Before generating or revising Narratiive strategy, every agent must:

1. Read `AGENTS.md` and its required governance documents.
2. Resolve the relevant canonical product sources.
3. Read the relevant files under `knowledge/`.
4. Treat `knowledge/handbook/` as canonical Narratiive strategic doctrine once a model is marked active.
5. Never use `narratiive/narratiive-knowledge` as a source of truth.

The former `narratiive/narratiive-knowledge` repository is deprecated. Its retained material is being curated into this repository rather than copied wholesale, because operating/runtime documents in that repository have been superseded by Narratiive OS.
