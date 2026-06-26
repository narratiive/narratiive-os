# Growth Blueprint

<!-- AI_TEMPLATE_ID: growth_blueprint -->
<!-- AI_TEMPLATE_VERSION: 1.0 -->
<!-- AI_POPULATION_MODE: replace_placeholders_only -->
<!-- AI_SOURCE_REQUIREMENT: use_provided_context_only -->

## Template Controls

- Client: {{client_name}}
- Prepared for: {{audience_or_stakeholder}}
- Prepared by: {{creator_name}}
- Date: {{date}}
- Version: {{version}}
- Source inputs: {{source_inputs}}

> Guidance: Populate this template only from approved source material. If information is missing, leave the placeholder in place or mark it as `{{needs_input:field_name}}`.

## Executive Summary

<!-- AI_SECTION: executive_summary -->
<!-- AI_INSTRUCTIONS: Summarize the growth blueprint using only populated sections below. Do not add unsupported claims. -->

{{executive_summary}}

## Business Context

<!-- AI_SECTION: business_context -->

### Current State

{{current_state}}

### Growth Objective

{{growth_objective}}

### Constraints and Assumptions

{{constraints_and_assumptions}}

> Guidance: Separate confirmed constraints from assumptions. Do not convert assumptions into facts.

## Audience

<!-- AI_SECTION: audience -->

### Primary Audience

{{primary_audience}}

### Secondary Audience

{{secondary_audience}}

### Audience Needs

{{audience_needs}}

### Audience Barriers

{{audience_barriers}}

## Positioning

<!-- AI_SECTION: positioning -->

### Category

{{category}}

### Core Promise

{{core_promise}}

### Differentiators

{{differentiators}}

### Proof Points

{{proof_points}}

> Guidance: Proof points must come from supplied evidence, testimonials, data, case studies, or approved claims.

## Growth Strategy

<!-- AI_SECTION: growth_strategy -->

### Strategic Thesis

{{strategic_thesis}}

### Priority Opportunities

{{priority_opportunities}}

### Growth Levers

{{growth_levers}}

### Risks

{{risks}}

## Channel Plan

<!-- AI_SECTION: channel_plan -->

| Channel | Role | Audience Segment | Message Focus | Activation Notes | KPI |
| --- | --- | --- | --- | --- | --- |
| {{channel_1}} | {{channel_1_role}} | {{channel_1_audience_segment}} | {{channel_1_message_focus}} | {{channel_1_activation_notes}} | {{channel_1_kpi}} |
| {{channel_2}} | {{channel_2_role}} | {{channel_2_audience_segment}} | {{channel_2_message_focus}} | {{channel_2_activation_notes}} | {{channel_2_kpi}} |
| {{channel_3}} | {{channel_3_role}} | {{channel_3_audience_segment}} | {{channel_3_message_focus}} | {{channel_3_activation_notes}} | {{channel_3_kpi}} |

## Messaging System

<!-- AI_SECTION: messaging_system -->

### Narrative Pillars

{{narrative_pillars}}

### Key Messages

{{key_messages}}

### Calls to Action

{{calls_to_action}}

### Language Guardrails

{{language_guardrails}}

## Measurement

<!-- AI_SECTION: measurement -->

### North Star Metric

{{north_star_metric}}

### Supporting Metrics

{{supporting_metrics}}

### Reporting Cadence

{{reporting_cadence}}

### Learning Questions

{{learning_questions}}

## Execution Roadmap

<!-- AI_SECTION: execution_roadmap -->

| Phase | Objective | Key Activities | Owner | Timing | Dependencies |
| --- | --- | --- | --- | --- | --- |
| {{phase_1}} | {{phase_1_objective}} | {{phase_1_key_activities}} | {{phase_1_owner}} | {{phase_1_timing}} | {{phase_1_dependencies}} |
| {{phase_2}} | {{phase_2_objective}} | {{phase_2_key_activities}} | {{phase_2_owner}} | {{phase_2_timing}} | {{phase_2_dependencies}} |
| {{phase_3}} | {{phase_3_objective}} | {{phase_3_key_activities}} | {{phase_3_owner}} | {{phase_3_timing}} | {{phase_3_dependencies}} |

## Open Inputs

<!-- AI_SECTION: open_inputs -->
<!-- AI_INSTRUCTIONS: List missing information required to complete this blueprint. -->

{{open_inputs}}

## AI Population Contract

```yaml
template_id: growth_blueprint
population_rules:
  - use_provided_context_only
  - preserve_headings
  - preserve_markers
  - replace_double_curly_placeholders_when_supported
  - leave_unknown_placeholders_unfilled
required_inputs:
  - client_name
  - growth_objective
  - primary_audience
  - positioning
  - growth_levers
  - measurement
output_format: markdown
```
