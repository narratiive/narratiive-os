---
title: Narratiive Growth Specification
version: 1.0
owner: Narratiive
status: canonical
object_type: growth_specification
machine_readable: true
---

# Narratiive Growth Specification v1.0

## Purpose

The Growth Specification is the canonical parent object for Narratiive's strategy-to-performance operating system. It connects strategic diagnosis, campaign world-building, creative direction, production planning, asset delivery and performance learning into one traceable lifecycle.

It is not a single client document. It is the system-level source of truth that Tony and future Narratiive agents use to determine what exists, what is approved, what is missing and what should happen next.

## Canonical Object Model

```text
Growth Specification
    |
    +-- Growth Blueprint
    +-- Campaign World
    +-- Creative Director's Bible
    +-- Production Pack
    +-- Asset Manifest
    +-- Performance Feedback
```

## Child Objects

### 1. Growth Blueprint

Answers: **What should the business do to create growth?**

Defines the commercial context, market understanding, audience, positioning, narrative, strategic choices, growth priorities and recommended system of action.

### 2. Campaign World

Answers: **What campaign universe should express the strategy?**

Translates the approved Growth Blueprint into a coherent creative platform, campaign territories, visual world, tone, still and motion directions, social expressions and channel translation principles.

Canonical schema:

`knowledge/campaign-world/campaign-world-schema-v1.md`

### 3. Creative Director's Bible

Answers: **Exactly how should the campaign look, feel, sound and behave?**

Turns the approved Campaign World into the production-grade creative source of truth for human teams and AI production systems.

Canonical specification:

`knowledge/creative-bible/creative-directors-bible-v2.md`

### 4. Production Pack

Answers: **How will each approved asset be made?**

Defines asset-level briefs, production methods, responsibilities, dependencies, formats, technical requirements, prompts, storyboards, schedules, review gates and handoff instructions.

Canonical specification:

`knowledge/production-pack/production-pack-specification-v1.md`

### 5. Asset Manifest

Answers: **What assets exist, where are they, and what state are they in?**

Provides a machine-readable register of planned, generated, reviewed, approved, delivered and superseded assets, including lineage back to strategy and creative direction.

Canonical specification:

`knowledge/asset-manifest/asset-manifest-specification-v1.md`

### 6. Performance Feedback

Answers: **What happened, what did we learn, and what should change?**

Connects campaign and asset performance to the original strategic choices, captures evidence and learning, and creates approved recommendations for the next iteration of the Growth Specification.

Canonical specification:

`knowledge/performance-feedback/performance-feedback-specification-v1.md`

## Shared Metadata Contract

Every Growth Specification and child object must expose the following metadata:

```yaml
id: string
object_type: string
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
parent_object_id: string | null
source_object_ids: list
child_object_ids: list
repository_path: string
commit_sha: string | null
```

## Lifecycle

```text
Draft
  -> In Review
  -> Approved
  -> Active
  -> Superseded or Archived
```

Child objects cannot become `active` unless their required parent inputs are `approved` or `active`.

Default dependencies:

```text
Growth Blueprint (approved)
  -> Campaign World
  -> Creative Director's Bible
  -> Production Pack
  -> Asset Manifest
  -> Performance Feedback
  -> approved learning feeds the next Growth Blueprint version
```

## Traceability Rules

1. Every child object must identify its parent and source objects.
2. Every production asset must trace back to an approved Production Pack item.
3. Every Production Pack item must trace back to the Creative Director's Bible and Campaign World.
4. Strategic claims must trace back to the Growth Blueprint or an explicitly named evidence source.
5. Performance learning must identify the campaign, asset, audience, channel, metric and observation period it describes.
6. Superseded objects remain addressable and must not be silently overwritten.

## Validation Principles

A Growth Specification is structurally complete only when:

- all six child object types are represented;
- required dependencies are valid;
- approved objects contain no unresolved critical validation errors;
- all active assets have lineage and ownership;
- repository paths and versions are recorded;
- status values use the shared lifecycle vocabulary.

Structural completeness does not mean commercial or creative approval. Approval remains a separate human-controlled state transition.

## Tony Orchestration Contract

Tony should reason over object state, not conversational memory.

When the user sends:

```text
progress update
```

Tony must read repository-backed project state and return:

```yaml
sprint_name: string
overall_status: string
completed: list
in_progress: list
next: list
blocked: list
latest_commit:
  sha: string
  message: string
  timestamp: datetime
open_decisions: list
```

Tony must distinguish between:

- `designed`: architecture agreed but no finished artefact exists;
- `authored`: finished artefact exists outside the canonical repository path;
- `committed`: artefact is present in Git with a verifiable commit;
- `operational`: runtime code actively reads or uses the artefact;
- `validated`: automated checks or a documented human acceptance test passed.

Tony must never infer completion from chat history alone. A repository commit, runtime state or explicit approval record is required.

## Current Canonical Coverage

| Object | Canonical artefact | Repository state |
|---|---|---|
| Growth Specification | This document | Committed |
| Growth Blueprint | Existing Narratiive OS blueprint system | Review and canonical path mapping required |
| Campaign World | `knowledge/campaign-world/campaign-world-schema-v1.md` | Committed |
| Creative Director's Bible | `knowledge/creative-bible/creative-directors-bible-v2.md` | Committed |
| Production Pack | `knowledge/production-pack/production-pack-specification-v1.md` | Committed |
| Asset Manifest | `knowledge/asset-manifest/asset-manifest-specification-v1.md` | Committed |
| Performance Feedback | `knowledge/performance-feedback/performance-feedback-specification-v1.md` | Committed |

## Next Canonical Milestones

1. Add machine-readable JSON Schemas for the parent and child objects.
2. Add validators for dependency, lifecycle and lineage rules.
3. Connect Tony's `progress update` intent to repository and runtime state.
4. Review and map the Growth Blueprint into its canonical repository path.

## Governance

Changes to the object model, lifecycle vocabulary, required child objects or approval rules are architectural changes and must be versioned.

Editorial improvements that do not alter meaning may be committed as patch updates.

Security-sensitive runtime configuration, credentials and private client data must never be stored in this knowledge specification.
