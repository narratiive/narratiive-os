# Tony — Chief of Staff Implementation Plan

Version: 1.0
Status: Delivery plan

## Objective

Implement a coherent executive layer over the existing Narratiive OS runtime. The work must reuse canonical stores, the public command gateway, workspace isolation, event sourcing and human approval boundaries.

## Delivery sequence

### 1. Executive message model

Create a structured manager-facing response object that can represent:

- observation;
- implication;
- recommendation;
- human effort;
- confidence;
- evidence references;
- urgency;
- interruption eligibility.

Replace generic status strings in `runtime/tony_orchestration.py` with outcome-oriented rendering while preserving the raw response data.

Acceptance tests:

- health, run, job and approval responses render business meaning;
- technical diagnostics remain available in response data;
- no stack trace, credential or provider internals appear in normal manager messages;
- existing idempotency and workspace-boundary tests continue to pass.

### 2. Morning Executive Brief read model

Add a deterministic read model that combines canonical state from:

- health and provider registries;
- active runs and jobs;
- approval queue;
- artifact catalogue;
- workspace events;
- future commercial and publishing adapters.

The first version should work with runtime data already available and explicitly mark unavailable external metrics rather than inventing them.

Output sections:

1. Business health.
2. Material changes.
3. Work completed.
4. Decisions waiting.
5. Biggest risk.
6. Biggest opportunity.
7. Three recommended actions.
8. Estimated human effort.

Acceptance tests:

- identical canonical state produces identical briefs;
- duplicate events are not double-counted;
- cross-workspace records are rejected;
- empty-state output remains useful and honest;
- recommendations include evidence references.

### 3. Friday Executive Review read model

Aggregate the previous seven days of append-only events into:

- completed outputs;
- approval throughput;
- blocked or retried work;
- workflow reliability;
- human interventions;
- significant wins;
- repeated themes;
- next-week recommendation.

Pattern detection must separate observations from hypotheses. A repeated-pattern claim requires three supporting records by default.

### 4. Mission Control contract

Expose a stable, read-only executive snapshot for a future UI or Notion view. The snapshot must not become a new source of truth.

Suggested top-level schema:

```json
{
  "generated_at": "ISO-8601",
  "workspace_id": "string",
  "health": {},
  "work": {},
  "approvals": {},
  "pipeline": {},
  "publishing": {},
  "risks": [],
  "opportunities": [],
  "recommended_focus": {},
  "recent_wins": []
}
```

Unavailable integrations should return an explicit `not_connected` state.

### 5. Interruption policy

Implement a deterministic policy that only flags immediate attention when one of the following is true:

- client commitment at risk;
- time-critical approval;
- material system failure;
- high-confidence commercial opportunity;
- imminent external deadline.

Everything else should be queued for the next Morning Brief or Friday Review.

## Repository architecture rules

- New commands must be added to the public command gateway before Tony can invoke them.
- Tony must not query private implementation stores directly when a public read action exists.
- All workspace-aware reads must require and validate `workspace_id` and `client_id` where applicable.
- Recommendations are advisory and must not bypass approval requirements.
- Generated executive outputs should be stored as immutable artifacts or deterministic projections with source lineage.
- Provider-generated interpretation must be separable from deterministic factual state.

## Proposed milestones

### Milestone A — Foundation

- Canonical Chief of Staff contract.
- Structured executive message model.
- Outcome-oriented health, run, job and approval messages.
- Unit tests for language and governance.

### Milestone B — Daily visibility

- Morning Brief projection.
- Public gateway read action.
- Telegram-ready renderer.
- Empty-state and degraded-state tests.

### Milestone C — Weekly intelligence

- Friday Review projection.
- Pattern/hypothesis distinction.
- Evidence-linked recommendations.
- Weekly renderer.

### Milestone D — Mission Control

- Read-only snapshot schema.
- API or gateway action.
- Notion or web presentation adapter.
- Integration-state visibility.

## Explicit non-goals for the first implementation

- Replacing Notion as the source of truth.
- Giving Tony independent authority to approve client-ready work.
- Adding a second orchestration pathway outside the gateway.
- Using an LLM to calculate factual system state.
- Claiming pipeline, audience or revenue metrics when no canonical adapter exists.
