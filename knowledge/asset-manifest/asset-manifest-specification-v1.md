---
title: Narratiive Asset Manifest Specification
version: 1.0
owner: Narratiive
status: canonical
object_type: asset_manifest
machine_readable: true
---

# Narratiive Asset Manifest Specification v1.0

## Purpose

The Asset Manifest is the canonical, machine-readable register of every planned, generated, reviewed, approved, delivered, superseded and archived campaign asset in Narratiive OS.

It answers four operational questions:

1. What assets should exist?
2. What assets currently exist?
3. Where is the authoritative version of each asset?
4. What state, lineage, ownership and approval history does each asset have?

The Asset Manifest is not a moodboard, production brief or file dump. It is the operational inventory that connects approved strategy and production instructions to real output files and their lifecycle.

## Position in the Growth Specification

```text
Growth Blueprint
  -> Campaign World
  -> Creative Director's Bible
  -> Production Pack
  -> Asset Manifest
  -> Performance Feedback
```

The Asset Manifest is created from an approved Production Pack and updated throughout production, review, delivery and optimisation.

## Canonical Responsibilities

The Asset Manifest must:

- register every required asset before production begins;
- assign a stable asset identity independent of filename or storage location;
- connect each asset to its Production Pack item and upstream strategic sources;
- record every produced variant and rendition;
- distinguish planned, working, approved and delivered files;
- preserve superseded versions rather than silently overwriting them;
- expose ownership, review status, approval history and delivery state;
- provide the authoritative inputs for performance reporting;
- allow Tony to identify missing, blocked, stale or unapproved assets.

## Manifest-Level Metadata

Every Asset Manifest must include:

```yaml
id: string
object_type: asset_manifest
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
  - production_pack_id
  - creative_bible_id
  - campaign_world_id
  - growth_blueprint_id
repository_path: string
commit_sha: string | null
storage_roots:
  working: uri
  approved: uri
  delivered: uri
asset_count:
  planned: integer
  in_production: integer
  in_review: integer
  approved: integer
  delivered: integer
  blocked: integer
  superseded: integer
```

## Asset Record Contract

Each asset record must expose:

```yaml
asset_id: string
asset_key: string
name: string
description: string
asset_type: string
purpose: string
campaign_role: string
production_pack_item_id: string
source_object_ids: list
parent_asset_id: string | null
variant_group_id: string | null
status: planned | queued | in_production | generated | in_review | changes_requested | approved | delivered | superseded | archived | blocked
priority: critical | high | medium | low
owner: string
producer: string | null
reviewer: string | null
approver: string | null
created_at: datetime
updated_at: datetime
review_due_at: datetime | null
approved_at: datetime | null
delivered_at: datetime | null
channel: string
placement: string
market: string | null
language: string | null
audience: string | null
funnel_role: string | null
format:
  file_type: string
  mime_type: string | null
  width: integer | null
  height: integer | null
  aspect_ratio: string | null
  duration_seconds: number | null
  file_size_bytes: integer | null
technical_requirements: list
creative_requirements: list
rights_and_usage:
  territory: string | null
  start_date: date | null
  end_date: date | null
  talent_restrictions: string | null
  music_restrictions: string | null
  licence_notes: string | null
storage:
  working_uri: string | null
  review_uri: string | null
  approved_uri: string | null
  delivered_uri: string | null
  thumbnail_uri: string | null
file_integrity:
  checksum: string | null
  checksum_algorithm: string | null
  source_filename: string | null
  canonical_filename: string | null
version:
  number: integer
  label: string
  supersedes_asset_id: string | null
  superseded_by_asset_id: string | null
approval:
  status: not_required | pending | approved | rejected
  approved_by: string | null
  approved_at: datetime | null
  approval_notes: string | null
validation:
  status: not_run | passed | failed | warning
  checks: list
  last_validated_at: datetime | null
blockers: list
tags: list
```

## Asset Identity

`asset_id` is immutable and must never be derived solely from a filename.

Recommended form:

```text
ast_<client>_<campaign>_<sequence>
```

Example:

```text
ast_rave_everyday-coffee_0042
```

`asset_key` is a human-readable operational key and should encode the asset family without becoming the unique identity.

Example:

```text
paid-social_meta_9x16_problem-solution_v01
```

Filenames may change. Storage locations may change. The asset identity must not.

## Asset Families and Variants

A single creative idea may generate multiple related outputs. The manifest must distinguish:

- **master asset**: the primary approved source;
- **variant**: a creative adaptation with meaningful content differences;
- **rendition**: a technical export of the same creative content;
- **version**: a sequential revision of one asset record;
- **derivative**: an asset created from another approved asset.

`parent_asset_id` records derivation. `variant_group_id` groups related assets that belong to the same creative family.

## Lifecycle

```text
Planned
  -> Queued
  -> In Production
  -> Generated
  -> In Review
  -> Approved
  -> Delivered
```

Alternative transitions:

```text
In Review -> Changes Requested -> In Production
Any active state -> Blocked
Approved or Delivered -> Superseded
Any terminal state -> Archived
```

An asset cannot become `approved` unless required validation checks pass or an authorised human explicitly records an exception.

An asset cannot become `delivered` unless an approved file URI exists.

## Required Validation Checks

Validation should be appropriate to asset type, but the system must support at least:

```yaml
- file_exists
- file_readable
- expected_file_type
- expected_dimensions
- expected_aspect_ratio
- expected_duration
- expected_language
- naming_convention
- required_brand_assets_present
- required_disclaimers_present
- rights_window_valid
- approval_record_present
- production_pack_lineage_valid
- checksum_recorded
```

Validation results must be stored against the asset record. Failed critical checks block approval.

## Traceability Rules

1. Every asset must reference one approved Production Pack item.
2. Every asset must inherit or explicitly override its Campaign World and Creative Bible sources.
3. Every delivered file must trace to an approved asset record.
4. Every performance observation must reference one or more Asset Manifest `asset_id` values.
5. Every variant and derivative must identify its parent or variant group.
6. Superseded assets remain addressable and retain their storage and approval history.
7. A filename collision must never silently replace an existing approved asset.
8. Manual uploads must be registered before they can be treated as canonical assets.

## Naming Convention

Recommended canonical filename structure:

```text
<client>_<campaign>_<channel>_<placement>_<concept>_<ratio-or-duration>_<market>_<language>_v<version>.<ext>
```

Example:

```text
rave_everyday-coffee_meta-reels_problem-solution_9x16_uk_en_v03.mp4
```

Naming conventions improve operability but do not replace immutable asset identity.

## Minimum Operational Views

Tony and other operators should be able to produce the following views from the manifest:

### Production Queue

Assets with status `queued`, `in_production`, `changes_requested` or `blocked`.

### Review Queue

Assets with status `generated` or `in_review`, ordered by priority and review deadline.

### Approval Register

Assets with current approval state, approver, timestamp and notes.

### Delivery Register

Approved assets with delivery URI, destination, delivered timestamp and recipient or channel.

### Missing Asset Report

Production Pack items without a corresponding Asset Manifest record, and planned assets without a produced file.

### Supersession Map

Current approved assets and all previous versions or derivatives.

## Tony Orchestration Contract

Tony should use the Asset Manifest to answer operational questions such as:

```text
What assets are missing?
What is ready for review?
What is blocked?
Which assets are approved but not delivered?
Which file is the current approved version?
What changed since the last review?
```

Tony must not infer asset status from chat messages, folder contents or filenames alone. The manifest record is authoritative.

Recommended structured response:

```yaml
campaign_id: string
manifest_version: string
summary:
  total: integer
  planned: integer
  in_production: integer
  in_review: integer
  approved: integer
  delivered: integer
  blocked: integer
material_items:
  - asset_id: string
    name: string
    status: string
    owner: string
    next_action: string
blockers: list
latest_update:
  timestamp: datetime
  changed_by: string
```

## Change and Version Rules

- Content revisions increment the asset version.
- Technical renditions may share a creative version but require distinct asset records when they are independently delivered or measured.
- Replacing an approved file requires a new version and explicit supersession link.
- Manifest schema changes follow semantic versioning.
- Asset records must not be deleted merely because a file is obsolete; use `superseded` or `archived`.

## Security and Privacy

The manifest may contain storage URIs and operational metadata, but must not contain:

- credentials or API keys;
- private access tokens;
- unrestricted signed URLs with long-lived access;
- personal data not required for production governance;
- confidential client material in a public repository.

Private client manifests should live in access-controlled storage while conforming to this canonical schema.

## Acceptance Criteria

An Asset Manifest is structurally valid when:

- manifest-level required metadata is present;
- every asset has a stable `asset_id`;
- every asset has valid Production Pack lineage;
- lifecycle values use the canonical vocabulary;
- approved assets contain an approved file URI and approval record;
- delivered assets contain a delivered URI and timestamp;
- superseded assets contain valid supersession links;
- critical validation failures are absent from approved assets;
- aggregate counts reconcile with asset records.

Structural validity does not replace creative, legal, client or commercial approval.

## Future Machine-Readable Implementation

The next implementation step is a JSON Schema that validates:

- manifest-level metadata;
- asset record shape;
- lifecycle values;
- lineage requirements;
- approval and delivery prerequisites;
- supersession relationships;
- aggregate count reconciliation.
