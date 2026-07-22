---
title: Narratiive Production Pack Specification
version: 1.0
owner: Narratiive
status: canonical
object_type: production_pack
machine_readable: true
---

# Narratiive Production Pack Specification v1.0

## Purpose

The Production Pack converts an approved Creative Director's Bible into executable asset-level instructions. It is the production contract used by human makers, AI generation systems, automation workflows and Tony to determine exactly what must be produced, how it should be produced, which inputs are authoritative, what dependencies exist and how completion is validated.

A Production Pack is not a moodboard, a campaign summary or a loose prompt library. It is a controlled set of production jobs with explicit ownership, technical requirements, approval gates and traceable lineage back to the Growth Specification.

## Required Inputs

A Production Pack may only become `active` when the following source objects are `approved` or `active`:

1. Growth Blueprint
2. Campaign World
3. Creative Director's Bible

Optional supporting inputs may include media plans, channel specifications, platform policies, legal guidance, product files, brand asset libraries, talent agreements, market adaptations and client comments.

## Canonical Object Model

```text
Production Pack
    |
    +-- Pack Metadata
    +-- Production Summary
    +-- Source Controls
    +-- Asset Jobs
    |     +-- Brief
    |     +-- Creative Direction
    |     +-- Technical Specification
    |     +-- Generation or Production Method
    |     +-- Dependencies
    |     +-- Review Gates
    |     +-- Handoff Requirements
    |
    +-- Shared Resources
    +-- Production Schedule
    +-- Responsibility Matrix
    +-- Risk and Compliance Register
    +-- Validation Record
    +-- Version History
```

## Pack Metadata

Every Production Pack must expose the shared Growth Specification metadata contract and the following production-specific fields:

```yaml
id: string
object_type: production_pack
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
source_object_ids: list
child_object_ids: list
repository_path: string
commit_sha: string | null
production_pack_name: string
production_owner: string
market_scope: list
channel_scope: list
planned_asset_count: integer
completed_asset_count: integer
critical_blockers: list
```

## Production Summary

The Production Summary provides a concise operational view of the pack:

- campaign objective;
- production objective;
- audience and market scope;
- approved creative platform;
- channel and format coverage;
- production approach;
- planned asset count;
- key dates;
- approval owner;
- current blockers;
- definition of done.

It must be possible for Tony to read this section and report pack state without interpreting the full creative document.

## Source Controls

The Production Pack must explicitly identify which upstream sources control each decision.

```yaml
source_controls:
  growth_blueprint:
    object_id: string
    version: string
    approved_at: datetime
    controls:
      - business_objective
      - audience
      - positioning
      - measurement_intent
  campaign_world:
    object_id: string
    version: string
    approved_at: datetime
    controls:
      - campaign_platform
      - territories
      - visual_world
      - tone_of_voice
      - channel_translation
  creative_bible:
    object_id: string
    version: string
    approved_at: datetime
    controls:
      - art_direction
      - copy_rules
      - casting
      - motion_language
      - sound_language
      - prohibited_expressions
```

Where sources conflict, the Production Pack must not silently choose. The conflict must be recorded as a blocker and escalated to the named approval owner.

## Asset Job Contract

Each planned asset is represented by one Asset Job. Asset Jobs are the smallest independently assignable and reviewable units in the Production Pack.

```yaml
asset_job:
  id: string
  asset_family_id: string | null
  title: string
  status: planned | ready | in_production | in_review | changes_requested | approved | delivered | cancelled | superseded
  priority: critical | high | medium | low
  owner: string
  reviewer: string
  due_at: datetime | null
  parent_production_pack_id: string
  source_object_ids: list
  source_section_refs: list
  market: string
  language: string
  channel: string
  placement: string
  asset_type: string
  format: string
  objective: string
  audience: string
  message_role: string
  creative_territory: string
  concept_name: string
  call_to_action: string | null
  inputs: list
  outputs: list
  dependencies: list
  review_gates: list
  validation_checks: list
  handoff_destination: string | null
  repository_path: string | null
  external_uri: string | null
  asset_manifest_id: string | null
```

## Asset Brief

Every Asset Job must answer:

1. What is being made?
2. Why does it exist?
3. Who is it for?
4. Where will it appear?
5. What single communication job must it perform?
6. Which approved campaign territory and concept does it express?
7. Which elements are mandatory?
8. Which elements are prohibited?
9. What must the audience think, feel or do?
10. What evidence will show the asset is acceptable?

A brief that cannot answer these questions is not production-ready.

## Creative Direction

Each Asset Job must carry only the creative direction required to make that asset correctly. It should reference canonical source sections rather than duplicating the entire Creative Director's Bible.

Required fields:

```yaml
creative_direction:
  proposition: string
  audience_takeaway: string
  emotional_response: string
  visual_principles: list
  composition: string
  subject_or_scene: string
  brand_codes: list
  copy_requirements: list
  tone_rules: list
  motion_rules: list
  sound_rules: list
  mandatory_elements: list
  prohibited_elements: list
  reference_assets: list
```

## Technical Specification

Technical requirements must be explicit enough for automated validation where possible.

```yaml
technical_specification:
  width_px: integer | null
  height_px: integer | null
  aspect_ratio: string | null
  duration_seconds: number | null
  frame_rate: number | null
  file_format: string
  codec: string | null
  max_file_size_mb: number | null
  colour_space: string | null
  audio_specification: string | null
  safe_area: string | null
  subtitle_requirement: string | null
  platform_constraints: list
  naming_convention: string
  accessibility_requirements: list
  localisation_requirements: list
```

Platform requirements must be versioned or dated where they are likely to change.

## Production Method

Each Asset Job must name its intended production method:

```text
human_production
ai_generation
ai_assisted_production
template_render
adaptation
localisation
composite
```

For AI-generated or AI-assisted work, the job must also specify:

```yaml
ai_production:
  provider: string
  model: string
  model_version: string | null
  prompt: string
  negative_prompt: string | null
  seed: string | null
  reference_inputs: list
  generation_parameters: object
  expected_variants: integer
  selection_rule: string
  human_review_required: true
```

Prompts are production instructions, not strategic sources. They must not introduce claims, audiences, territories or visual rules that are absent from approved upstream objects.

## Storyboards and Shot Lists

Motion assets longer than a single simple shot must include a storyboard or shot list.

```yaml
shot:
  shot_id: string
  sequence: integer
  duration_seconds: number
  framing: string
  action: string
  camera_movement: string | null
  dialogue_or_voiceover: string | null
  on_screen_copy: string | null
  sound: string | null
  transition: string | null
  source_reference: string
```

The total shot duration must equal the intended asset duration within the allowed delivery tolerance.

## Dependencies

Dependencies may include:

- approved copy;
- product photography;
- logos and brand assets;
- pack shots;
- legal claims;
- talent or location approval;
- music licensing;
- source footage;
- localisation copy;
- platform specifications;
- media trafficking requirements;
- another Asset Job.

Each dependency must record an owner, status and blocking severity.

```yaml
dependency:
  id: string
  description: string
  owner: string
  status: open | ready | blocked | waived
  blocking: boolean
  due_at: datetime | null
  source_uri: string | null
```

An Asset Job cannot move to `ready` while a blocking dependency is unresolved.

## Review Gates

Default review gates are:

```text
Brief Ready
  -> Production Ready
  -> First Output Review
  -> Creative Approval
  -> Technical QA
  -> Delivery Approval
```

Every gate must name:

- gate owner;
- required evidence;
- pass criteria;
- status;
- timestamp;
- comments;
- resulting state transition.

Human approval is mandatory for creative approval and delivery approval unless an explicit client-approved exception exists.

## Responsibility Matrix

The pack must distinguish accountability from execution.

```yaml
responsibility_matrix:
  accountable: string
  production_owner: string
  creative_reviewer: string
  technical_reviewer: string
  legal_reviewer: string | null
  client_approver: string | null
  delivery_owner: string
```

Tony may coordinate, monitor, report and route work. Tony must not represent creative, legal or client approval unless the corresponding approval event is recorded.

## Production Schedule

The schedule must contain:

- pack start date;
- final delivery date;
- Asset Job due dates;
- dependency deadlines;
- review windows;
- market or channel sequencing;
- contingency allowance;
- current schedule risk.

Schedule changes that affect committed delivery dates must create a versioned change record.

## Shared Resources

Shared production resources may include:

- approved logos;
- typography files or references;
- colour values;
- product files;
- photography;
- footage;
- music;
- sound effects;
- legal copy;
- disclosure language;
- templates;
- prompt components;
- reference outputs.

Each resource must have a stable identifier, source location, usage rights where relevant and version.

## Risk and Compliance Register

The Production Pack must capture foreseeable production risks, including:

- unsupported or unverified claims;
- missing usage rights;
- talent consent;
- trademark misuse;
- market-specific legal requirements;
- platform policy risk;
- synthetic-media disclosure;
- unsafe or misleading AI output;
- inaccessible delivery;
- privacy or personal-data exposure;
- production schedule risk;
- technical non-compliance.

Critical risks prevent approval until resolved or explicitly accepted by an authorised human.

## Handoff Requirements

Each completed Asset Job must provide:

```yaml
handoff:
  final_files: list
  source_files: list
  preview_files: list
  copy_document: string | null
  technical_report: string | null
  rights_record: string | null
  delivery_destination: string
  delivered_at: datetime | null
  delivered_by: string | null
  asset_manifest_id: string
```

No delivered asset is complete until it is registered in the Asset Manifest.

## Validation Rules

A Production Pack is structurally valid only when:

1. all required metadata fields are present;
2. source objects are approved or active;
3. every Asset Job has an owner, reviewer, objective, channel, format and source lineage;
4. every Asset Job has technical requirements appropriate to its format;
5. all blocking dependencies are resolved before production begins;
6. all required review gates are recorded;
7. approved assets have passed creative and technical review;
8. delivered assets have an Asset Manifest identifier;
9. no critical compliance risk remains unresolved;
10. superseded jobs retain version history and lineage.

## Tony Orchestration Contract

Tony should use the Production Pack to answer:

- Which assets are planned?
- Which jobs are ready to start?
- Which jobs are blocked, by what and by whom?
- Which outputs are awaiting review?
- Which approvals are missing?
- Which assets are late or at risk?
- Which assets have been delivered?
- Which delivered assets are missing from the Asset Manifest?

Tony may perform the following non-approval transitions when validation permits:

```text
planned -> ready
ready -> in_production
in_production -> in_review
approved -> delivered
```

Tony must not perform:

```text
in_review -> approved
changes_requested -> approved
critical risk -> waived
```

unless an authorised human approval record exists.

## Definition of Done

A Production Pack is complete when:

- every planned Asset Job is delivered, cancelled or superseded;
- every delivered asset is registered in the Asset Manifest;
- all mandatory approvals are recorded;
- all critical risks are resolved or formally accepted;
- handoff destinations and final files are recorded;
- the pack's final validation record passes;
- the final pack version is committed to the canonical repository path.

## Canonical Repository Path

```text
knowledge/production-pack/production-pack-specification-v1.md
```

Client-specific Production Packs must not be stored in the canonical knowledge directory. They should be generated into an approved client or campaign workspace with private data handled according to Narratiive security policy.

## Versioning and Governance

Changes to required fields, status vocabularies, review gates, validation rules or approval authority require a version increment.

Editorial improvements that do not alter behaviour may be committed as patch updates.

Production Pack specifications must never contain credentials, API keys, private client data or unlicensed source assets.