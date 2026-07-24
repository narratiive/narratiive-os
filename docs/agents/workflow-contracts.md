# Narratiive OS Workflow Contracts

Status: Repository contribution and operational handoff contract

## Repository workflow

### 1. Inspect

Before changing a file:

- confirm the repository root, branch, worktree state, and relevant history;
- read `AGENTS.md`, applicable role instructions, and `docs/agents/`;
- read the owning stream's source, tests, README, workflow, template, and canon;
- identify generated/local files and unrelated changes to preserve.

### 2. Scope

State:

- requested outcome and exclusions;
- owning workstream and affected workstreams;
- contracts and canonical terminology involved;
- approval class;
- evidence, lineage, immutable-history, workspace, security, and client risk.

If the task would require a new architecture, product rename, canon change,
cross-client access, history rewrite, or approval bypass, stop and route the
decision before implementation.

Classify governance changes using `decision-authority.md`:

- substantive changes receive the full applicable review;
- non-substantive documentation changes receive lightweight independent review;
- uncertain changes are substantive.

### 3. Branch

- Never edit `main` directly.
- Create or use a task branch based on the current approved base.
- Reuse existing branch vocabulary where suitable: `docs/…`, `feat/…`,
  `fix/…`, or `agent/…`.
- Keep one coherent purpose per branch.
- Do not discard, rewrite, or absorb unrelated local work.

These are repository policies. GitHub branch protection, rulesets, required
approvals, status checks, and push restrictions are repository configuration.
The checkout does not prove those settings are enabled. Configuration gaps do
not waive policy; see `decision-authority.md`.

### 4. Implement

- Follow the owning stream and the smallest existing boundary.
- Preserve compatibility and terminology.
- Write additive migrations and histories.
- Keep credentials and private client content out of the repository.
- Add or update tests when observable behaviour changes.
- Update affected contracts when the approved behaviour changes.

### 5. Verify

Use checks proportionate to risk. Runtime changes normally require:

```bash
python -m unittest discover -s tests -v
```

Documentation-only changes require at minimum:

- link/path and heading review;
- terminology and contradiction review;
- diff inspection;
- confirmation that no runtime or canonical product content changed
  unintentionally.

### 6. Pull request

The author provides:

- concise outcome and rationale;
- owned and affected streams;
- files and contracts changed;
- tests/checks and exact results;
- compatibility or migration notes;
- assumptions, open questions, and residual risk;
- required reviewers and human approval;
- explicit statement when client-facing outputs are affected.

### 7. Independent review

- The author cannot approve their own work.
- An AI agent cannot approve or merge its own work through another identity,
  session, or automation.
- Review must come from a qualified party other than the author.
- Cross-stream changes require each affected stream owner.
- Client-facing work requires an authorised human.
- Constitutional, product-canon, or material architecture changes require Matt
  in addition to specialist review.

### 8. Merge and release

- No agent merges its own pull request.
- Merge is performed only by an authorised human or independently authorised
  maintainer after required approvals and checks.
- Merge approval is not permission to send, publish, export, or production-run a
  client-facing output; release approval is recorded separately.
- The release record references the approved artefact version. Later edits
  require a new version and, for client-facing changes, renewed human approval.

## Operational pipeline contract

### Stage handoff

Every handoff contains:

- workspace ID, client ID, workflow ID, run ID, and stage ID;
- exact input and parent artefact IDs;
- source/evidence references and permissions;
- applicable agent contract, prompt version, template, and canon bundle;
- facts, interpretations, assumptions, open inputs, constraints, and prior
  review findings relevant to the receiving specialist;
- expected output type and success/failure contract.

Only context relevant and permitted for the receiving specialist is included.
Memory selection follows the established specialist policy.

### Completion

A stage completes only when:

- it was the ready/running current stage;
- required inputs existed;
- a non-empty validated output was written;
- the immutable output was registered with lineage;
- the state snapshot and append-only event history were updated;
- the next stage was evaluated or the approval gate was entered.

A pipeline is not client-releasable merely because all specialist stages are
complete.

### Growth Specification lifecycle

Growth Specification objects follow the contract in
`knowledge/growth-specification/README.md` and the shared schema in
`schemas/shared/growth-object.schema.json`.

- Validate type, lifecycle, identity, path, approval, and reciprocal
  relationships before treating an object as canonical.
- Child objects cannot become `active` until required parent inputs are
  `approved` or `active`.
- Production Pack items trace to approved creative direction; Asset Manifest
  entries trace to Production Pack items; Performance Feedback names the
  campaign, asset, audience, channel, metric, and observation period.
- `approved` and `active` are explicit recorded states. Neither repository
  presence, structural validity, nor a Tony progress report grants approval.
- Supersession creates a new addressable version and preserves prior lineage.
- Tony selects the next action from validated object and repository state. An
  `in_review` object routes to human review; invalid canonical state blocks
  dispatch.

### Retry and revision

- A retry reruns the responsible stage after a recoverable failure.
- A revision names one deterministic owner and invalidates that stage and its
  downstream dependants.
- Prior raw responses, artefacts, reviews, scores, comments, and events remain.
- The complete revised chain is revalidated; a partial fix does not inherit
  approval automatically.
- Repeated failure without new evidence or a resolvable change becomes blocked.

### Approval

Client-facing outputs include, at minimum:

- Growth Blueprints and derivative decks;
- Campaign Worlds;
- Creative Director's Bibles;
- Narratiive Signals and outreach emails;
- presentation exports;
- speculative or production creative;
- prompts or briefs sent to a production provider;
- approved Production Pack jobs or assets released for production;
- any content sent, published, or presented under Narratiive or a client name.

They require:

1. specialist completion;
2. Quality Reviewer verdict at the applicable threshold;
3. resolution of blocking findings;
4. an authorised human decision against the exact artefact version;
5. append-only recording of reviewer identity, rationale, comments, and outcome.

Agents may prepare drafts and approval packages. They may not impersonate the
human decision.

## Existing tool and workflow governance

This section governs only tools and handoffs already present in code or
documentation. It does not assert that a documented external integration is
installed or available.

### Git, GitHub, and CI

- Git changes follow the branch, pull-request, independent-review, and merge
  policies in the Constitution.
- `.github/workflows/runtime-tests.yml` runs Python compilation and the existing
  unit suite on Python 3.12 when pull requests or pushes to `main` change
  `runtime/**`, `tests/**`, `schemas/**`, or that workflow file.
- A successful workflow is test evidence, not review, merge authority, or
  client-release approval.
- Branch protection and required approvals depend on GitHub configuration and
  must be verified separately by an authorised administrator.

### Local scripts

- `scripts/run_pipeline.py` is for the deterministic pipeline and fixtures.
- `scripts/run_live_pipeline.py` invokes the same stages through the existing
  OpenAI-compatible live-provider boundary.
- `scripts/deploy_specialists.py` publishes and activates the existing specialist
  definitions through the prompt registry.
- `scripts/import_blueprint_canon.py` imports and versions the existing Blueprint
  canon and manifest.
- `scripts/tony_gateway_cli.py` invokes the existing authenticated Tony/runtime
  command boundary.
- `scripts/service_doctor.py`, `scripts/service_supervisor.py`, and
  `scripts/recover_tony_services.py` diagnose and narrowly recover the existing
  per-user services.
- `scripts/install_launch_agents.py` and `scripts/run_with_env.py` install the
  existing LaunchAgent definitions and load their external environment safely.
- `scripts/deploy_tony_runtime.py` verifies and deploys an explicit repository
  revision; `scripts/operational_acceptance.py` records the existing live
  acceptance checks.

Operators use explicit repository, runtime, workspace/client, fixture, run, and
model inputs required by each script. Synthetic fixture output is not client
evidence. A script's successful exit does not grant canon approval, client
approval, or permission to publish. Canon import follows the substantive
product-canon decision class.

### Mission Control, Tony, OpenClaw, Telegram, and n8n

Tony and n8n use the structured public command gateway. They preserve workspace
and client identity, correlation, idempotency, run state, and approval gates.
They do not manipulate persistence directly or translate operational access into
specialist, review, or human-release authority.

Mission Control and Tony's repository status, client, next-action, brief,
capability, diagnostic, history, and explanation commands are deterministic and
evidence-backed. They report repository/runtime state and do not infer
completion from chat. Missing configuration is shown as unavailable or blocked,
not guessed.

`openclaw/tony_http_bridge.py` is the authenticated OpenClaw, Telegram, and n8n
boundary. Telegram slash commands use deterministic Tony services; managerial
actions continue through `TonyOrchestrationAdapter` and the public gateway.
`openclaw/tony_live_bridge.py` composes the live executive and capability
services without expanding their authority.

The execution journal is append-only and hash-chained. Workspace state events
are append-only and replayable, while atomic snapshots are derived current
state. Neither store may be rewritten to conceal a prior decision or event.

### Schemas, ADRs, operations, and examples

- `schemas/` contains machine-readable contracts consumed by validators and CI.
  A schema change that alters accepted objects or lifecycle meaning is
  substantive and requires Delivery Engine compatibility review.
- `docs/adr/` records accepted architecture decisions. An ADR documents a
  decision; it does not grant an author permission to implement or deploy it.
- `docs/operations/` and `docs/service-supervisor.md` document existing operator
  procedures. Procedures do not weaken authentication, approval, or
  append-only evidence requirements.
- `examples/` contains synthetic input shapes only. Examples are not production
  client records, proof of integration, or permission to process private data.

### Deployment, diagnostics, and recovery

The current operational surface manages the runtime gateway, Tony bridge, and
service supervisor as per-user macOS LaunchAgents. Credentials and environment
values remain outside Git, are loaded without shell evaluation, and use the
documented restrictive file mode.

Deployment is tied to an explicit revision and succeeds only after verification
and live health checks. Recovery follows `docs/adr/0001-service-recovery-policy.md`:
stable diagnostic exit codes, command argument arrays without a shell, one
unhealthy service at a time, bounded retries, and structured evidence. Unknown
states fail closed. A receipt proves the observed operational action; it is not
client, product, canon, or release approval.

### Providers and model routing

- Deterministic providers are for fixtures and dry runs.
- Live providers use the existing OpenAI-compatible clients and explicit
  capability, health, policy, and fallback records.
- Endpoint and credential values remain runtime configuration; credentials are
  not persisted in prompts, routing metadata, events, or artefacts.
- Provider output is untrusted until the existing response, artefact, lineage,
  quality, and approval checks pass.
- Selecting a fallback provider does not permit a model or product change outside
  the approved routing policy.

### Research adapters

Web retrieval and local-document ingestion use the existing evidence source
policy and safety boundaries. Operators supply approved sources, permissions,
allowlists, and workspace/client context. Retrieval success does not establish
truth: evidence remains labelled, deduplicated, traceable, and subject to the
responsible specialist's review.

### Prompt registry and specialist deployment

Prompt publication creates a version; activation selects an explicit version.
Rollback changes the active selection without erasing prompt history. Specialist
deployment must match the existing agent and workflow contracts. A prompt or
deployment change that alters behaviour is substantive even when no runtime
source file changes.

### Blueprint canon and presentation export

Blueprint canon is resolved through its checksum-validated manifest. Import or
version changes follow canon governance and never overwrite approved history.

The existing Claude Slides adapter is an export boundary. Export attempts and
versions remain immutable and workspace-scoped; credentials are not persisted.
Export success does not mean the deck is approved or released. Client use
requires human approval for the exact artefact version.

### Documented external production handoffs

The product and specialist documents refer to Higgsfield, Sora, Veo, image
generation, and Gmail drafting. These references describe intended downstream
handoffs; this repository does not by itself establish that every integration is
implemented or connected.

Use of an available external production tool requires explicit task authority,
approved inputs, the existing evidence and lineage record, and workspace/client
scope. Generated creative and email drafts remain unapproved client-facing
outputs until the Quality Reviewer and authorised human gates are complete.
Tools must not send, publish, or production-run work merely because generation
or export succeeded.

## Decision routing

The canonical role definitions are in `ai-constitution.md`. The review and
decision matrix, including substantive and non-substantive governance changes,
is in `decision-authority.md`.

## Handoff report

Every completed contribution reports:

- what changed and what did not;
- assumptions;
- checks and results;
- affected streams and reviewers still required;
- any discrepancy discovered but intentionally left unchanged;
- confirmation that no commit, push, merge, release, or dispatch occurred unless
  each action was explicitly authorised.
