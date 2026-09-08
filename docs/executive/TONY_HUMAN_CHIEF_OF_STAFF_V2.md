# Tony Human Chief of Staff v2

## Product objective

Tony's primary product surface is a reasoned, continuous conversation with Matt. Deterministic commands, workflow state, Notion and specialist agents are implementation details behind that surface.

The current failure mode is a split brain: the repository intends ordinary Telegram language to route to OpenClaw, but executive reporting still behaves like a projection of all visible state, and natural-language housekeeping has no guaranteed persisted business-state effect. The result is conversational acknowledgement without agency, or silence, followed by repetitive database-shaped briefs.

This tranche should fix the product behaviour rather than add more phrase matching.

## 1. Natural language must always get a conversational response

Canonical routing remains:

- ordinary language -> OpenClaw Tony agent
- explicit slash command -> deterministic command surface

Do not reintroduce a legacy phrase parser for ordinary language.

For every authenticated ordinary-language Telegram message Tony must either:

1. answer/reason conversationally;
2. perform an authorised internal action and report verified evidence; or
3. explain the blocker/missing capability and propose the smallest next step.

Silence is never a successful outcome.

Acceptance probes should include typos, pronouns, follow-ups and non-canonical wording.

## 2. Give OpenClaw a safe internal attention-management capability

Implement a canonical, persisted attention/disposition layer rather than relying on prompt memory. Reuse existing Notion/runtime fields where semantically correct; do not create competing sources of truth.

Required dispositions/equivalents:

- active
- watching
- needs_human_attention
- suppressed
- test
- archived/closed

Persist reason, actor, timestamp and evidence of the mutation. Suppression/archive must be reversible. Deletion remains a distinct consequential operation and must never be inferred from "ignore", "retire", "archive" or "don't show me".

Expose the safe reversible actions to Tony's OpenClaw control plane so ordinary language can resolve to deterministic internal effects after entity resolution.

Required conversational behaviours:

- "Tony, retire or archive all the test responses please."
- "Rave isn't a real lead; keep it as a test but stop showing it in the commercial pipeline."
- "Don't show me Northstar again."
- "Show me what you've suppressed."
- "Restore Rave to the attention queue."
- "Ignore the old SAFE tests."

For an ambiguous genuine entity, ask before mutation. For an unambiguous batch selected by explicit SAFE/test markers, a reversible internal suppression/test disposition may proceed within the existing safe-internal-action boundary.

## 3. Executive briefs are change/exception products, not snapshots

Persist a briefing checkpoint so the renderer can distinguish first-seen, changed, unchanged and resolved items across restarts.

Default morning brief:

### Needs you
Only decisions/approvals where Matt's judgement is genuinely required. Rank by commercial consequence.

### Since last brief
Material new or changed business state. Aggregate routine volume.

### Tony is handling
A compact aggregate of healthy autonomous work. Expand only on request.

### Blocked
Only unresolved blockers with a real consequence. Do not duplicate an item already shown elsewhere.

### Recommendation
At most one highest-value recommendation. Omit when there is no useful recommendation.

Zero-value sections should disappear.

Default exclusions:

- SAFE/test/synthetic records
- suppressed records
- archived/closed records
- completed workflows with no pending action
- unchanged records already reported
- healthy autonomous work that requires no intervention

A record is "new" only when first observed after the previous successful checkpoint, not because its Notion status contains the word New.

Scale requirement: 5, 50, 500 and 5,000 records must not cause linear message growth. Cap named actionable items at three by default and summarise overflow as a count.

## 4. Salience is a first-class behaviour

Rank attention using, at minimum:

1. consequential human approval/decision;
2. genuine commercial opportunity;
3. client/delivery risk;
4. blocked revenue/workflow;
5. material change;
6. routine autonomous work;
7. test/engineering housekeeping.

Test and engineering records must not displace real commercial opportunities in Matt's brief.

## 5. Conversation and business state must connect

OpenClaw owns interpretation and continuity. Narratiive OS owns authoritative state and effects. A natural-language instruction that changes attention state therefore requires both layers:

`Matt's message -> OpenClaw interpretation/context -> safe control-plane intent -> entity resolution -> deterministic persisted mutation -> returned evidence -> conversational acknowledgement`

Do not let OpenClaw claim a state change based only on conversational memory.

## 6. Proactive behaviour

Tony should use available connected business context to surface meaningful consequences, but should not manufacture work. Examples:

- If a genuinely warm diagnostic arrives, explain why it merits attention and recommend the next action.
- If a workflow is healthy, handle it quietly.
- If an expected client/research deliverable stalls, surface the consequence rather than raw system status.
- If a previously reported blocker resolves, stop reporting it; mention the resolution once only when useful.

## 7. Acceptance suite

Add deterministic and live-safe tests proving:

- arbitrary ordinary language reaches OpenClaw;
- ordinary-language failures return an explicit useful response rather than silence;
- contextual follow-up references are preserved;
- "archive/retire all test responses" persists reversible disposition changes;
- ambiguous entity mutation fails safely;
- "restore" reverses suppression;
- restart preserves dispositions and briefing checkpoint;
- 50 ordinary records do not create a 50-item brief;
- SAFE/test records are excluded by default;
- completed workflows with no pending action are excluded;
- unchanged items are not repeatedly called new;
- a newly arrived genuine warm lead is surfaced;
- a consequential approval is surfaced;
- one blocker is not duplicated across sections;
- resolved blocker disappears appropriately;
- no external client action is performed by these attention-management operations.

Include a live-safe Telegram acceptance probe using synthetic records only.

## 8. Migration/cleanup

After the capability is deployed, perform a one-time safe cleanup of existing explicit SAFE/test/synthetic records so they are classified as test/suppressed from executive briefs without deleting historical evidence. Rave remains a controlled test subject unless Matt explicitly promotes it. Do not touch genuine commercial leads through heuristic matching alone.

## Definition of done

Matt can talk to Tony in ordinary English as he would to a chief of staff. Tony responds, reasons, can carry out safe reversible internal housekeeping with verified persistence, and produces short exception-based briefs whose length is driven by decisions rather than database size.

This work must not weaken human approval gates for outreach, meetings, proposals, delivery, invoicing, publication, external sharing or other consequential actions.