# Campaign World

<!-- AI_TEMPLATE_ID: campaign_world -->
<!-- AI_TEMPLATE_VERSION: 1.0 -->
<!-- AI_POPULATION_MODE: replace_placeholders_only -->
<!-- AI_SOURCE_REQUIREMENT: use_provided_context_only -->

## Template Controls

- Campaign name: {{campaign_name}}
- Client: {{client_name}}
- Prepared for: {{audience_or_stakeholder}}
- Prepared by: {{creator_name}}
- Date: {{date}}
- Version: {{version}}
- Source inputs: {{source_inputs}}

> Guidance: This is a reusable campaign world template. Populate only from approved strategy, creative, brand, product, and audience inputs.

## Campaign Overview

<!-- AI_SECTION: campaign_overview -->

### Campaign Purpose

{{campaign_purpose}}

### Business Objective

{{business_objective}}

### Audience Objective

{{audience_objective}}

### Desired Audience Shift

{{desired_audience_shift}}

## Strategic Foundation

<!-- AI_SECTION: strategic_foundation -->

### Audience

{{audience}}

### Insight

{{insight}}

### Tension

{{tension}}

### Opportunity

{{opportunity}}

### Single-Minded Proposition

{{single_minded_proposition}}

> Guidance: Keep this section evidence-led. Do not create an insight, tension, or proposition unless it is supplied or clearly derivable from source material.

## Campaign World

<!-- AI_SECTION: campaign_world -->

### World Premise

{{world_premise}}

### World Rules

{{world_rules}}

### Emotional Territory

{{emotional_territory}}

### Cultural Context

{{cultural_context}}

### Symbols and Motifs

{{symbols_and_motifs}}

### Characters, Roles, or Archetypes

{{characters_roles_or_archetypes}}

## Creative Platform

<!-- AI_SECTION: creative_platform -->

### Campaign Idea

{{campaign_idea}}

### Tagline or Line System

{{tagline_or_line_system}}

### Message Pillars

{{message_pillars}}

### Proof Points

{{proof_points}}

### Calls to Action

{{calls_to_action}}

## Expression System

<!-- AI_SECTION: expression_system -->

### Voice

{{voice}}

### Visual Direction

{{visual_direction}}

### Motion or Interaction Direction

{{motion_or_interaction_direction}}

### Content Formats

{{content_formats}}

### Do and Do Not

| Do | Do Not |
| --- | --- |
| {{do_1}} | {{do_not_1}} |
| {{do_2}} | {{do_not_2}} |
| {{do_3}} | {{do_not_3}} |

## Channel Activation

<!-- AI_SECTION: channel_activation -->

| Channel | Role in Campaign World | Creative Use | Primary Asset Types | Notes |
| --- | --- | --- | --- | --- |
| {{channel_1}} | {{channel_1_role}} | {{channel_1_creative_use}} | {{channel_1_asset_types}} | {{channel_1_notes}} |
| {{channel_2}} | {{channel_2_role}} | {{channel_2_creative_use}} | {{channel_2_asset_types}} | {{channel_2_notes}} |
| {{channel_3}} | {{channel_3_role}} | {{channel_3_creative_use}} | {{channel_3_asset_types}} | {{channel_3_notes}} |

## Asset Architecture

<!-- AI_SECTION: asset_architecture -->

### Hero Assets

{{hero_assets}}

### Supporting Assets

{{supporting_assets}}

### Modular Components

{{modular_components}}

### Adaptation Rules

{{adaptation_rules}}

## Measurement

<!-- AI_SECTION: measurement -->

### Campaign KPIs

{{campaign_kpis}}

### Creative Learning Questions

{{creative_learning_questions}}

### Reporting Cadence

{{reporting_cadence}}

## Production Notes

<!-- AI_SECTION: production_notes -->

### Dependencies

{{dependencies}}

### Approvals

{{approvals}}

### Risks

{{risks}}

### Open Inputs

{{open_inputs}}

## AI Population Contract

```yaml
template_id: campaign_world
population_rules:
  - use_provided_context_only
  - preserve_headings
  - preserve_markers
  - replace_double_curly_placeholders_when_supported
  - leave_unknown_placeholders_unfilled
required_inputs:
  - campaign_name
  - client_name
  - campaign_purpose
  - audience
  - insight
  - campaign_idea
  - channel_activation
output_format: markdown
```
