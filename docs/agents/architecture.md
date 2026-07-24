# Narratiive OS Architecture

Status: Current-state description
Scope: Repository architecture; no new runtime design

## System purpose

Narratiive OS is a workspace-scoped, evidence-led workflow system for producing
and reviewing strategic and creative artefacts. Its principal documented
pipeline is:

`Research Analyst → Strategy Director → Campaign World Generator → Creative Director → Quality Reviewer`

The corresponding artefact chain is:

`research inputs → Growth Blueprint → Campaign World → Creative Director's Bible → quality review`

Client-ready workflows enter human approval after the final quality stage.

## Repository map

| Path | Existing responsibility |
| --- | --- |
| `agents/` | Specialist and Orchestrator operating contracts |
| `workflows/` | Human-readable workflow specifications and executable JSON definitions |
| `runtime/` | Workflow, persistence, dispatch, provider, approval, research, Blueprint, Growth Object, Mission Control, and Tony command implementation |
| `scripts/` | Pipeline, deployment, diagnostics, recovery, supervision, installation, acceptance, and CLI entry points |
| `tests/` | Executable behaviour and regression contracts |
| `knowledge/blueprint/` | Checksum-locked Narratiive Growth Blueprint production canon |
| `knowledge/growth-specification/` | Canonical parent object for the strategy-to-performance lifecycle |
| `knowledge/campaign-world/` | Campaign World schema v1 |
| `knowledge/creative-bible/` | Creative Director's Bible v2 specification |
| `knowledge/production-pack/` | Production Pack specification v1 |
| `knowledge/asset-manifest/` | Asset Manifest specification v1 |
| `knowledge/performance-feedback/` | Performance Feedback specification v1 |
| `schemas/` | Shared machine-readable Growth Object metadata, lifecycle, and lineage contract |
| `templates/` | Stable, marker-bearing Markdown output structures |
| `products/narratiive-signal/` | Canon for the external Narratiive Signal product |
| `clients/` | Client-scoped context and working state |
| `research/` | Research artefacts and source notes |
| `prompts/` | Repository location for reusable prompt material |
| `openclaw/` | Authenticated Tony HTTP/live bridges for OpenClaw, Telegram, and n8n |
| `docs/adr/` | Accepted architecture decisions |
| `docs/operations/` | Operational installation and acceptance instructions |
| `docs/service-supervisor.md` | Narrow service-recovery operating guide |
| `examples/` | Synthetic, non-client input templates |
| `.github/workflows/` | Path-scoped Tony runtime validation on pull requests and `main` |

## Core workflow runtime

### Definition and state

- `runtime/definitions.py` loads executable workflow JSON into ordered stage
  definitions.
- `runtime/models.py` defines workflow, stage, and artefact identities and the
  established status vocabulary.
- `runtime/state_machine.py` is a pure transition engine. It performs no model or
  network calls.
- `runtime/run_service.py` applies transitions and records workflow events.

The executable `workflows/growth_blueprint_pipeline.json` declares the five
specialists and `approval_required: true`.

### Persistence and audit

- `FileWorkflowRunRepository` stores atomic JSON snapshots.
- `JsonlEventLog` stores append-only, run-partitioned workflow events.
- `FileMemoryStore` stores client journals as checksum-chained, append-only JSONL.
- `FileArtifactCatalog` stores content by SHA-256 checksum and writes immutable,
  versioned lineage records with parent artefact IDs and producer metadata.
- `FilePromptRegistry` versions prompts within workspace scope.

Snapshots describe current state; events, memory journals, prompt versions, and
artefact records preserve how that state was reached. A snapshot is never a
substitute for audit history.

### Dispatch and execution

- `DispatchService` validates current-stage readiness and creates dispatch jobs.
- `FileDispatchQueue` owns job state and leases.
- `WorkerRunner` claims a lease and delegates execution to an `AgentExecutor`.
- `ExecutionPackageBuilder` assembles the agent contract, allowed context,
  relevant memory, prompt metadata, and upstream artefacts.
- `ProviderExecutor` calls a provider, validates its response, writes output, and
  registers immutable artefact lineage before completing the stage.

`DeterministicProvider` supports fixtures and dry runs. Live execution uses
OpenAI-compatible provider clients. Provider routing is explicit:
`ProviderCapabilityRegistry`, `ProviderHealthRegistry`, `RoutingPolicy`, and
`ModelRouter` select a declared healthy target and ordered fallback. Unreported
health fails closed. Credential values are read at request time and are not
persisted.

### Revision, scoring, and approval

- `ConfidenceEngine` produces an advisory scorecard; it does not replace Quality
  Reviewer policy or human approval.
- `RevisionRouter` resolves a deterministic specialist owner, and
  `RevisionService` invalidates only that stage and its downstream dependants.
- Prior artefact versions remain in the catalogue.
- `ApprovalService` reconstructs approval records from events. Comments and
  decisions are append-only, and command IDs support replay without duplicate
  audit events.
- A client-ready final stage moves the workflow to `awaiting_approval`; an
  authorised approval decision moves it to `complete`.

## Workspace isolation and public boundary

- `WorkspaceRuntimeManager` creates one physical runtime root per workspace and
  binds it to one client identity.
- Runs, events, jobs, memory, prompts, artefacts, and approvals are scoped to that
  runtime.
- Cross-workspace references are rejected.
- Legacy migration copies data into a workspace without deleting the source.

`RuntimeCommandAPI` is the structured application boundary for Tony, n8n, and
future interfaces. `WorkspaceCommandAPI` routes workspace-scoped requests and
retains legacy compatibility. The WSGI and production gateway layers provide
HTTP handling, bearer authentication, bounded request bodies, correlation IDs,
and idempotency.

Tony's adapter maps manager-facing actions onto this public command gateway; it
does not reach through it to persistence internals. Repository-backed,
read-only/operator commands may instead be handled deterministically by the Tony
command services described below.

## Specialist ownership

- **Research Analyst:** gathers and labels authorised evidence; does not recommend
  strategy.
- **Strategy Director:** populates the Growth Blueprint and makes supported
  strategic choices; does not invent evidence or unsupported tactics.
- **Campaign World Generator:** translates approved strategy into a campaign
  world; does not default to final executional assets.
- **Creative Director:** turns the Campaign World into production-ready creative
  direction; does not generate final assets by default.
- **Quality Reviewer:** audits the whole chain and routes findings; does not
  silently repair the work.
- **Orchestrator:** controls readiness, state, handoffs, and failure routing; does
  not create deliverables.

## Blueprint-specific path

The repository also contains a structured Narratiive Growth Blueprint path:

1. `ResearchEngine` retrieves or ingests approved sources, deduplicates evidence,
   and stores an immutable evidence pack with lineage.
2. `BlueprintKnowledgeRegistry` resolves the active, checksum-validated canon
   bundle from `knowledge/blueprint/manifest.json`.
3. `BlueprintOrchestrator` combines request, evidence, prompt identity, provider
   routing identity, and canon into a structured 30-slide Blueprint and records
   raw and structured artefacts.
4. `BlueprintVisualMapper` converts the structured Blueprint into renderable acts
   and slides using the canonical schema and visual intelligence libraries while
   retaining lineage.
5. `BlueprintPresentationExporter` records immutable export attempts through the
   existing Claude Slides adapter boundary.

The canonical master is exactly 30 slides across six acts. Five-slide Executive
Summary and ten-slide Diagnostic Teaser outputs are derivatives of that master,
not separate products.

## Growth Specification object model

`knowledge/growth-specification/README.md` defines the Growth Specification as
the canonical parent object for the strategy-to-performance lifecycle:

`Growth Specification → Growth Blueprint → Campaign World → Creative Director's Bible → Production Pack → Asset Manifest → Performance Feedback`

Every object shares repository, client/campaign, lifecycle, approval, parent,
source, child, and commit metadata. The common machine-readable contract is
`schemas/shared/growth-object.schema.json`.

- `GrowthObjectValidator` validates required metadata, object and lifecycle
  values, approval fields, safe repository paths, and reciprocal relationships.
- `RepositoryProgressEngine` derives campaign progress from the seven canonical
  object types instead of conversational memory.
- `TonyDispatcher` selects one deterministic next action and blocks dispatch
  when canonical validation fails. An `in_review` object routes to human review.
- Canonical statuses are `draft`, `in_review`, `approved`, `active`,
  `superseded`, and `archived`.
- Child objects cannot become active until their required parent inputs are
  approved or active.

The lifecycle specifications define distinct responsibilities:

- **Production Pack:** executable asset jobs, source controls, dependencies,
  production method, technical requirements, review gates, handoff, and
  responsibility matrix.
- **Asset Manifest:** stable asset identity, versions, variants, storage,
  validation, approval, delivery, and supersession records.
- **Performance Feedback:** sources, metrics, findings, confidence, approved
  recommendations, and reusable learning with causality guardrails.

The repository records implementation maturity explicitly. The parent Growth
Specification and child specifications are committed; the shared schema,
validator, progress engine, and Tony command surfaces are implemented and
tested. The Growth Specification's own coverage table still records Blueprint
canonical-path mapping as requiring review, and the Creative Director's Bible v2
file is labelled `draft_system_specification`. Governance must not promote
`designed`, `authored`, or `committed` work to `operational` or `validated`
without the required evidence.

The original five-stage workflow and Markdown templates still exist. They are
not silently interchangeable with the newer Growth Specification child-object
specifications; an approved, versioned reconciliation is required where their
contracts differ.

## Mission Control and Tony command services

Mission Control is an evidence-backed, read-only view assembled from canonical
repository progress, workstream state, connection state, approvals, and
blockers. It reports `healthy`, `partial`, `blocked`, or `empty` from recorded
state; it does not infer completion.

The deterministic Tony command surface includes:

- repository health, status/progress, client list/detail, and next-action
  commands;
- Mission Control and daily morning/evening briefs;
- capability/help output that marks commands unavailable when dependencies are
  not configured;
- diagnostics/service-doctor output;
- append-only execution history and decision explanation when the execution
  journal is configured.

`ExecutionJournal` preserves autonomous decision provenance as an append-only,
hash-chained journal. `WorkspaceStateRepository` preserves append-only workspace
events with deterministic replay and atomic snapshots. These are additional
current-state/audit stores; they do not replace the workflow event, memory, or
artefact contracts described above.

`openclaw/tony_http_bridge.py` provides the authenticated boundary for OpenClaw,
Telegram, and n8n. Telegram slash commands use deterministic repository services
and do not depend on a managerial language model. Manager actions continue
through `TonyOrchestrationAdapter` and the public runtime gateway.
`openclaw/tony_live_bridge.py` composes executive brief and capability services
onto the same bridge.

## Operational services

The repository supports three per-user macOS LaunchAgents:

- authenticated Narratiive runtime gateway;
- Tony HTTP bridge;
- service supervisor.

Operational scripts install/uninstall LaunchAgents, read a mode-`0600`
environment file without a shell, run health and deployment diagnostics, perform
an operational acceptance check, deploy a verified repository revision, and
recover only the unhealthy service.

ADR 0001 fixes the narrow recovery policy: use stable service-doctor exit codes,
execute restart commands as argument arrays without a shell, reject unknown
codes, avoid indefinite retries, and preserve structured/append-only recovery
records where configured. Deployment and recovery receipts under runtime state
prove which revision passed live health checks; they are operational evidence,
not source files or approval.

## Product path: Narratiive Signal

`products/narratiive-signal/` is an independent product canon within Narratiive
OS. Its internal workflow name is `Opportunity Card Pipeline`; its external
product name is `Narratiive Signal`.

Tony orchestrates. Claude researches, reasons, and writes. Higgsfield renders
speculative creative. Tony stores, validates, versions, and routes work to human
approval. That allocation must not be inferred as permission for Tony to rewrite
strategy or for Claude to release work.

## Architectural invariants

- ordered specialist ownership and explicit state transitions;
- ordered Growth Specification objects with validated parent/source/child
  relationships and lifecycle states;
- workspace/client isolation;
- safe identifiers and bounded repository paths;
- atomic current-state writes;
- append-only event and memory history;
- immutable, content-addressed, versioned artefacts;
- complete source and parent lineage;
- explicit provider capability, health, and routing identity;
- idempotent external commands;
- deterministic, repository-backed Mission Control and Tony status commands;
- fail-closed capability, diagnostics, deployment, and recovery behaviour;
- targeted downstream invalidation on revision;
- explicit human approval for client-facing release;
- canonical templates and checksum-locked Blueprint assets.

## Known documentation discrepancy

`workflows/growth_blueprint_pipeline.md` retains
`AI_AUTOMATION_STATUS: not_implemented` from its original specification phase.
The current repository contains executable workflow JSON, runtime services,
workers, providers, scripts, and tests implementing the pipeline. Until that
older document is deliberately revised, agents must not use its historical
metadata to claim that the runtime is absent.

`knowledge/growth-specification/README.md` also retains “next milestone” entries
for a shared schema, validators, Tony progress integration, and Blueprint
mapping. The first three now have implementation and test evidence in
`schemas/`, `runtime/`, and `tests/`; Blueprint canonical-path mapping remains
listed as requiring review. Agents must report the observed implementation
state without silently rewriting that canonical specification or claiming the
unresolved mapping is complete.
