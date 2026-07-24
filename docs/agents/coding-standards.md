# Narratiive OS Coding Standards

Status: Existing-convention baseline

These standards describe conventions already present in the repository. They do
not introduce a framework, formatter, database, or deployment architecture.

## Change discipline

- Inspect the relevant implementation, tests, contracts, and history first.
- Prefer the smallest change that satisfies the approved contract.
- Preserve public commands, dataclass fields, enum values, serialised shapes,
  file locations, and legacy compatibility unless an approved migration changes
  them.
- Do not mix governance, product-canon, client-content, and runtime changes in
  one pull request unless the cross-stream dependency requires it and is declared.
- Never edit generated `.runtime/`, virtual environment, cache, or bytecode
  content as source.
- Do not clean unrelated working-tree changes.

## Python baseline

- Support Python 3.10 or newer. CI currently verifies Python 3.12.
- Use the standard library unless a dependency is already established and
  justified by the task.
- Follow the existing use of type annotations, `dataclass`, `Enum`, `Protocol`,
  `pathlib.Path`, and explicit domain exceptions.
- Prefer narrow components with injected dependencies over hidden global state.
- Keep pure state transitions separate from network, provider, and filesystem
  effects.
- Use immutable records (`frozen=True`) for events, identities, lineage, and
  persisted value objects where the existing model does.
- Validate required strings and safe identifiers at boundaries.
- Use timezone-aware UTC timestamps.

## Persistence and integrity

- Current-state JSON writes must be atomic where the existing repository uses
  temporary files, flush/fsync, and replace.
- Event and memory journals are append-only JSONL. Never open them for in-place
  correction.
- Tony execution history and workspace state events are append-only and
  hash-chained or replayable according to their existing contracts. Snapshots
  are derived state and do not replace those histories.
- Preserve memory sequence, previous checksum, and checksum validation.
- Artefact content is content-addressed. Register a new version rather than
  overwriting a prior artefact or record.
- Include workspace, client, run, stage, producer, parent artefact, prompt,
  provider/model, and canon identity where the relevant model supports it.
- Migration copies before it deprecates; the existing legacy workspace migration
  does not delete its source.
- Serialised output must be deterministic where checksums or replay depend on it.
- Growth Objects use `schemas/shared/growth-object.schema.json`, safe
  repository-relative paths, reciprocal relationships, and the canonical
  lifecycle vocabulary. Do not invent aliases or infer approval.

## Runtime boundaries

- `WorkflowEngine` remains free of model, network, and filesystem calls.
- External callers use command or gateway boundaries; they do not manipulate
  repositories to simulate business actions.
- Dispatch jobs use the queue and lease contract.
- Provider selection uses declared capabilities, health, policy, and explicit
  fallbacks. Do not add a hidden fallback.
- Credentials are read from environment/runtime configuration at request time
  and never persisted or logged.
- Workspace and client identity are validated before resolving runs, jobs,
  memory, artefacts, prompts, or approvals.
- Retry and replay must not create duplicate completion, artefact, or approval
  events.
- Mission Control and Tony status/next-action commands derive results from
  repository and runtime evidence, not conversational memory.
- OpenClaw, Telegram, and n8n enter through the authenticated bridge or public
  command gateway; they do not acquire direct persistence or approval authority.

## Product and template handling

- Preserve canonical Markdown headings, marker comments, tables, YAML blocks,
  section order, and placeholder syntax.
- Unsupported fields remain placeholders or become explicit
  `{{needs_input:field_name}}` entries.
- Product canon and `knowledge/blueprint/manifest.json` components are not
  casual implementation fixtures.
- Tests and fixtures must not contain real client secrets or unapproved private
  material. Synthetic fixtures must remain visibly synthetic.
- British spelling and existing Narratiive editorial conventions should be
  retained in product-facing documentation.
- Examples remain synthetic and contain no real client credentials, identities,
  or private evidence.

## Operational services

- Environment and credential files remain outside Git, are loaded without shell
  evaluation, and use mode `0600` where the existing LaunchAgent workflow
  requires it.
- Deployment verifies an explicit repository revision and writes a receipt only
  after live health checks pass.
- Service recovery follows ADR 0001: stable diagnostic exit codes, argument
  arrays without a shell, narrow restart scope, bounded retries, and structured
  records.
- Health, capability, and dependency failures fail closed. A successful
  diagnostic or restart is operational evidence, not product or release
  approval.
- Architecture policy changes receive a versioned ADR under `docs/adr/`;
  operator procedures belong under `docs/operations/`.

## Testing

Use the established full-suite command:

```bash
python -m unittest discover -s tests -v
```

For a focused change, run the relevant test module during development and the
full suite before pull-request handoff when practical.

Tests should cover the observable contract, including relevant failure paths:

- valid and invalid state transitions;
- missing inputs and blocked states;
- job lease and retry behaviour;
- idempotent command replay and conflict;
- cross-workspace rejection;
- append-only/checksum integrity;
- immutable artefact versions and lineage;
- provider failure, capability, health, and fallback;
- revision ownership and downstream invalidation;
- approval queue, comments, decisions, and human gate;
- template, canon, and output validation.
- Growth Object metadata, lifecycle, dependency, and reciprocal lineage;
- repository progress, deterministic Tony routing, Mission Control, and briefs;
- authenticated bridge, diagnostics, deployment, supervision, and recovery
  failure paths.

Do not weaken a test to accommodate a regression. If an approved contract has
changed, update the implementation, test, and documentation together.

## Pull-request quality

Every pull request identifies:

- owning stream and affected streams;
- purpose and scope;
- architecture or product contract affected;
- tests run and results;
- migration or compatibility impact;
- evidence, lineage, immutability, approval, security, and client-isolation risk;
- assumptions and unresolved decisions;
- required independent reviewers.

Review and merge authority is defined canonically in `ai-constitution.md` and
routed by `decision-authority.md`.
