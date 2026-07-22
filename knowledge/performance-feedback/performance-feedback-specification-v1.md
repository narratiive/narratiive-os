---
title: Narratiive Performance Feedback Specification
version: 1.0
owner: Narratiive
status: canonical
object_type: performance_feedback
machine_readable: true
---

# Narratiive Performance Feedback Specification v1.0

## Purpose

Performance Feedback is the canonical learning object that connects campaign and asset results back to the strategic choices that produced them.

It answers four questions:

1. What happened?
2. Why might it have happened?
3. What have we learned with sufficient confidence?
4. What should change in the next approved iteration?

Performance Feedback must not become a dashboard dump or an automated source of strategic certainty. It separates observation, analysis, inference, recommendation and approval so Tony can report evidence without overstating what the evidence proves.

## Position in the Growth Specification

```text
Growth Blueprint
  -> Campaign World
  -> Creative Director's Bible
  -> Production Pack
  -> Asset Manifest
  -> Performance Feedback
  -> approved learning informs the next Growth Blueprint version
```

Performance Feedback reads from the approved Asset Manifest, media and platform results, research, commercial outcomes and explicitly recorded contextual events.

## Canonical Responsibilities

The object must:

- define the measurement period and comparison basis;
- record source provenance and data freshness;
- connect every result to campaign, asset, audience, market, channel and objective where applicable;
- distinguish delivered metrics from calculated metrics;
- preserve observations separately from interpretations;
- assign confidence and evidence strength to findings;
- identify conflicting or incomplete evidence;
- produce recommendations with owners, timing and approval state;
- preserve rejected recommendations and the reason for rejection;
- create traceable inputs for the next strategy, campaign or production iteration;
- allow Tony to report what is known, uncertain, blocked and awaiting approval.

## Object-Level Metadata

```yaml
id: string
object_type: performance_feedback
version: string
client_id: string
client_name: string
campaign_id: string
campaign_name: string
status: draft | in_review | approved | active | superseded | archived
created_at: datetime
updated_at: datetime
created_by: string
approved_by: string | null
approved_at: datetime | null
parent_object_id: string
source_object_ids:
  - asset_manifest_id
  - production_pack_id
  - creative_bible_id
  - campaign_world_id
  - growth_blueprint_id
repository_path: string
commit_sha: string | null
measurement_window:
  start_at: datetime
  end_at: datetime
  timezone: string
comparison_window:
  start_at: datetime | null
  end_at: datetime | null
reporting_currency: string | null
data_freshness_at: datetime
```

## Evidence Source Contract

Every source must be registered before its data can support a finding.

```yaml
source_id: string
source_type: platform | analytics | research | finance | crm | survey | experiment | manual | external
name: string
provider: string
uri: string | null
retrieved_at: datetime
covers_start_at: datetime
covers_end_at: datetime
granularity: campaign | asset | placement | audience | market | customer | aggregate
owner: string
status: available | partial | delayed | invalid | superseded
quality:
  completeness: high | medium | low | unknown
  reliability: high | medium | low | unknown
  known_limitations: list
  methodology_notes: string | null
```

Credentials, private customer-level data and platform secrets must never be stored in this object.

## Metric Record Contract

```yaml
metric_id: string
name: string
canonical_name: string
objective_id: string | null
metric_type: input | delivery | attention | engagement | consideration | conversion | revenue | efficiency | brand | operational | quality
value: number | string | null
unit: string
calculation: string | null
source_id: string
campaign_id: string
asset_id: string | null
placement: string | null
channel: string | null
market: string | null
audience: string | null
period_start_at: datetime
period_end_at: datetime
benchmark:
  type: target | historical | control | category | platform | none
  value: number | string | null
  source_id: string | null
variance:
  absolute: number | null
  percentage: number | null
validation:
  status: not_run | passed | warning | failed
  checks: list
notes: string | null
```

Metrics with different definitions, attribution windows or denominators must not be silently combined.

## Finding Contract

A finding is a structured claim supported by one or more metric records and evidence sources.

```yaml
finding_id: string
finding_type: observation | interpretation | inference | conclusion
statement: string
scope:
  campaign_id: string
  asset_ids: list
  channels: list
  markets: list
  audiences: list
  period_start_at: datetime
  period_end_at: datetime
supporting_metric_ids: list
supporting_source_ids: list
contradicting_metric_ids: list
confidence: high | medium | low | unknown
evidence_strength: experimental | causal_model | correlational | directional | anecdotal
materiality: critical | high | medium | low
limitations: list
requires_human_review: boolean
review_status: pending | accepted | amended | rejected
reviewed_by: string | null
reviewed_at: datetime | null
```

## Recommendation Contract

```yaml
recommendation_id: string
statement: string
recommendation_type: continue | stop | increase | reduce | revise | test | investigate | no_change
source_finding_ids: list
target_object_type: growth_blueprint | campaign_world | creative_bible | production_pack | asset_manifest | media_plan | measurement_plan
target_object_id: string | null
priority: critical | high | medium | low
expected_effect: string
risk: string
effort: low | medium | high
owner: string
next_action: string
due_at: datetime | null
approval_status: proposed | in_review | approved | rejected | implemented
approved_by: string | null
approved_at: datetime | null
implemented_at: datetime | null
rejection_reason: string | null
```

A recommendation cannot alter an approved upstream object until its approval state is `approved` and the resulting object change is versioned.

## Learning Record Contract

Only accepted findings and approved recommendations may become reusable learning.

```yaml
learning_id: string
statement: string
source_finding_ids: list
source_recommendation_ids: list
scope: client | category | audience | channel | format | campaign | asset
valid_from: datetime
review_by: datetime | null
confidence: high | medium | low
status: candidate | approved | superseded | rejected
approved_by: string | null
supersedes_learning_id: string | null
```

Client-specific evidence must not be generalised into a category-wide rule without an explicit review and scope change.

## Lifecycle

```text
Draft
  -> In Review
  -> Approved
  -> Active
  -> Superseded or Archived
```

Operational flow:

```text
Sources Registered
  -> Metrics Validated
  -> Findings Proposed
  -> Human Review
  -> Recommendations Approved or Rejected
  -> Approved Learning Published
  -> Next Object Version Created
```

## Validation Rules

The object is structurally valid only when:

1. the measurement window is explicit;
2. every metric references a registered source;
3. every asset-level metric references an Asset Manifest record;
4. metric definitions and calculation methods are recorded where derived;
5. every finding cites supporting evidence;
6. confidence and evidence strength are present for every finding;
7. limitations and contradictory evidence are preserved;
8. every recommendation references at least one reviewed finding;
9. no proposed recommendation is represented as implemented;
10. approved learning has a named approver and valid scope;
11. source freshness and quality are recorded;
12. superseded findings and learning remain addressable.

## Attribution and Causality Guardrails

- Platform attribution is evidence of attributed outcomes, not automatic proof of incrementality.
- Correlation must not be described as causation.
- Changes observed after launch must not be attributed solely to the campaign when material external factors exist.
- Cross-channel totals must account for overlap or state that overlap is unknown.
- Brand and commercial effects outside the measurement window must not be treated as zero.
- Missing data must remain missing; it must not be converted into a negative result.
- Automated analysis may propose interpretations, but high-materiality conclusions require human review.

## Tony Orchestration Contract

Tony may use Performance Feedback to answer:

```text
What happened?
What worked?
What underperformed?
What do we know with confidence?
What is still uncertain?
What should we do next?
Which recommendations need approval?
Which approved learning should update the strategy?
```

Tony must return findings grouped by evidence strength and must clearly distinguish:

- observed result;
- interpretation;
- approved conclusion;
- proposed action;
- approved action;
- unresolved uncertainty.

Tony must never present a proposed or low-confidence inference as established fact.

## Minimum Viable Performance Feedback

A valid first implementation requires:

- one registered source;
- one explicit measurement window;
- validated metrics tied to campaign or asset IDs;
- at least one reviewed finding;
- at least one recommendation with approval state;
- documented limitations;
- lineage to the Asset Manifest and Growth Blueprint.

## Governance

Changes to evidence levels, approval rules, lifecycle states, causality guardrails or the learning publication process require a versioned specification update.

Editorial clarifications that do not alter meaning may be committed as patch updates.
