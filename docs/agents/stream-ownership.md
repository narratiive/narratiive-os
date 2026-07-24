# Narratiive OS Stream Ownership

Status: Repository workstream boundaries

## How to read “forbidden”

An owned folder is the stream's primary responsibility. A forbidden folder is
outside that stream's unilateral edit authority. It may be changed only when the
task explicitly crosses streams, the pull request declares the dependency, and
the owning stream reviews it.

Root `README.md` is a shared integration surface. The nearest owning stream
reviews folder-level README changes. Future repository-wide tooling is a shared
surface requiring Executive Layer and Worker Infrastructure review.

## A. Executive Layer

**Purpose**

Define authority, governance, architecture intent, workstream boundaries,
decision rights, approval policy, and the rules followed by every contributor.

**Authority source**

Role authority is defined in `ai-constitution.md`; governance decisions are
routed by `decision-authority.md`.

**Owned folders and files**

- `AGENTS.md`
- `CLAUDE.md`
- `docs/agents/`
- `docs/adr/`

**Forbidden without cross-stream scope**

- `runtime/`, `scripts/`, `tests/`, `.github/workflows/`, `openclaw/`,
  `schemas/`, `docs/operations/`
- `products/`, `clients/`, `research/`, `examples/`
- `agents/`, `workflows/`, `templates/`, `prompts/`, `knowledge/`

**Expected outputs**

- governance contracts;
- role and approval matrices;
- current-state architecture documentation;
- architecture decision proposals;
- accepted architecture decision records;
- cross-stream dependency and risk decisions.

**Dependencies**

- runtime and tests for implementation truth;
- product canon for product truth;
- operational evidence from Tony;
- final decisions from Matt.

**Review requirements**

- Apply the substantive or non-substantive governance path in
  `decision-authority.md`.
- Include every affected stream when an Executive Layer change alters a boundary.

## B. Worker Infrastructure

**Purpose**

Implement and verify the workspace-scoped workflow runtime, persistence,
dispatch, workers, providers, routing, command gateway, approvals, research and
Blueprint services, Growth Object validation, Mission Control, Tony command
services, authenticated operational bridges, export boundaries, scripts, and
CI.

**Authority source**

Role authority is defined in `ai-constitution.md`; technical decisions are
routed by `decision-authority.md`.

**Owned folders and files**

- `runtime/`
- `scripts/`
- `tests/`
- `.github/workflows/`
- `openclaw/`
- `schemas/`
- `docs/operations/`
- `docs/service-supervisor.md`

**Forbidden without cross-stream scope**

- `AGENTS.md`, `CLAUDE.md`, `docs/agents/`
- `docs/adr/`
- `products/`, `clients/`, `research/`, `examples/`
- `agents/`, `workflows/`, `templates/`, `prompts/`, `knowledge/`

**Expected outputs**

- tested runtime components and public command boundaries;
- validated Growth Objects and repository-backed progress;
- deterministic Mission Control, Tony commands, briefs, and execution history;
- authenticated bridges and narrow deployment, diagnostics, supervision, and
  recovery instructions;
- safe persistence, dispatch, provider, approval, and workspace behaviour;
- migrations that preserve history and compatibility;
- automated tests and CI evidence;
- technical handoff and operational run instructions.

**Dependencies**

- Executive Layer architecture and approval constraints;
- Delivery Engine agent, workflow, template, prompt, and canon contracts;
- Commercial Engine client/product inputs;
- Tony's operational command requirements.

**Review requirements**

- Apply the runtime/configuration decision class in `decision-authority.md`.
- Add affected-stream review for changed delivery contracts, client data, or
  client-facing output.
- Provide full relevant test evidence before merge.

## C. Commercial Engine

**Purpose**

Own commercial products, approved prospect/client context, outreach material,
and research inputs that establish why work should exist and for whom.

**Authority source**

Role authority is defined in `ai-constitution.md`; commercial, canon, and release
decisions are routed by `decision-authority.md`.

**Owned folders and files**

- `products/`
- `clients/`
- `research/`
- `examples/`

**Forbidden without cross-stream scope**

- `AGENTS.md`, `CLAUDE.md`, `docs/agents/`
- `runtime/`, `scripts/`, `tests/`, `.github/workflows/`
- `agents/`, `workflows/`, `templates/`, `prompts/`, `knowledge/`, `schemas/`

**Expected outputs**

- approved product specifications and editorial contracts;
- client/prospect briefs, permissions, source inventories, and state;
- evidence packs and research notes;
- synthetic intake examples that carry no private client data;
- Narratiive Signal work packages, quality reports, and approval packages;
- commercial outcomes and open-input records.

**Dependencies**

- Executive Layer approval and decision rights;
- Worker Infrastructure for workspace isolation, lineage, orchestration, and
  approval records;
- Delivery Engine for specialist production and templates;
- Matt's target, commercial, and release decisions.

**Review requirements**

- Apply the commercial, product-canon, or client-release decision class in
  `decision-authority.md`.
- Evidence permissions and Quality Reviewer findings remain part of the review
  package.

## D. Delivery Engine

**Purpose**

Define how approved evidence becomes strategy, campaign territory, creative
direction, quality review, and renderable Blueprint output.

**Authority source**

Leadership authority is defined in `ai-constitution.md`. Specialist stage
ownership remains defined by the applicable agent and workflow contracts.
Delivery decisions are routed by `decision-authority.md`.

**Owned folders and files**

- `agents/`
- `workflows/`
- `templates/`
- `prompts/`
- `knowledge/`

**Forbidden without cross-stream scope**

- `AGENTS.md`, `CLAUDE.md`, `docs/agents/`
- `runtime/`, `scripts/`, `tests/`, `.github/workflows/`, `openclaw/`,
  `schemas/`, `docs/operations/`
- `docs/adr/`
- `products/`, `clients/`, `research/`, `examples/`

**Expected outputs**

- stable specialist and Orchestrator contracts;
- executable and human-readable workflow definitions;
- canonical templates and prompt versions;
- checksum-validated Narratiive Growth Blueprint canon;
- Growth Specification, Growth Blueprint, Campaign World, Creative Director's
  Bible, Production Pack, Asset Manifest, Performance Feedback, and
  quality-review contracts;
- derivative and production handoff specifications.

**Dependencies**

- Commercial Engine evidence, client context, permissions, and product purpose;
- Worker Infrastructure for execution, persistence, provider routing, lineage,
  revision, approval, and export;
- Executive Layer for boundaries and exceptions;
- human product and client decisions.

**Review requirements**

- Apply the specialist/workflow/template/prompt decision class in
  `decision-authority.md`.
- Include the specialist owner and runtime compatibility evidence.
- Client-facing release follows the separate human-release decision class.

## Cross-stream change protocol

A pull request touching more than one stream must:

1. name one coordinating stream;
2. list every affected owned path and owner;
3. explain why the change cannot remain inside one stream;
4. document contract, migration, evidence, lineage, and approval impact;
5. receive the independent review routed by `decision-authority.md`.
