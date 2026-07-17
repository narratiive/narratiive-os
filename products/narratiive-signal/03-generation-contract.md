# Narratiive Signal — Generation Contract

Version: 1.0
Status: Canonical

## Instruction to the generating model

Before generating any Narratiive Signal, read every canonical file in `products/narratiive-signal/`.

Treat those files as the source of truth. Do not invent new sections, rename the product, weaken the evidence standard or replace the editorial voice with generic agency language.

## Required process

1. Confirm the company, recipient, objective and available evidence.
2. Research the company, category, customers, competitors and communications using approved public sources.
3. Separate facts, interpretations and assumptions.
4. Generate at least three candidate observations internally.
5. Select the observation that is most specific, consequential, ownable and creatively fertile.
6. Build one coherent argument from observation to evidence to white space to creative direction.
7. Draft the Signal using the canonical structure.
8. Draft the outreach email.
9. Define the speculative campaign world and production prompts.
10. Score the work using `04-quality-rubric.md`.
11. Revise any dimension scoring below the threshold.
12. Return the complete output package with internal evidence notes.

## Required output schema

Return these sections in this order:

### A. Internal work record

- Company
- Recipient
- Role
- Website
- Signal number
- Date
- Sources
- Material facts
- Interpretations
- Assumptions and confidence
- Rejected candidate observations
- Selected central insight and rationale

### B. Outreach email

- Subject line
- Email body

### C. Narratiive Signal

- Cover/header
- Personal opening
- What we noticed
- Why we think that
- The white space
- If this were ours...
- What we'd be careful about
- A speculative campaign world
- Invitation

### D. Creative production brief

For each asset:

- asset type and duration/format;
- strategic role;
- concept;
- scene or composition;
- casting/subjects where relevant;
- location;
- lighting and texture;
- camera or movement;
- sound where relevant;
- product and branding behaviour;
- exclusions and failure modes;
- final Higgsfield-ready prompt.

### E. Quality report

- score by dimension;
- total score;
- failed gates;
- revisions made;
- final approval recommendation.

## Non-negotiable rules

- One central insight, not a list of recommendations.
- Every material claim must be evidenced or clearly framed as interpretation.
- Public evidence only unless private client material has been explicitly approved.
- No invented quotes, numbers, customer attitudes or competitor activity.
- No generic praise, fake familiarity or personalisation theatre.
- No direct claim that Narratiive can guarantee growth.
- No hard meeting request or artificial urgency.
- No finished asset may expose internal scoring, prompts, placeholders or source scaffolding.

## Tony orchestration contract

Tony should:

1. identify the next approved company in the lead or outreach queue;
2. resolve the latest canonical version of this folder;
3. give Claude the company context, evidence permissions and required files;
4. store the raw model response and source lineage immutably;
5. run the quality rubric and review checklist;
6. return failed work to Claude with specific deficiencies;
7. launch approved creative briefs through Higgsfield;
8. assemble the final document and Gmail draft;
9. notify the human approver;
10. record approval, edits, dispatch and outcome.

Tony must not silently rewrite strategic content. Strategic revisions return to Claude; orchestration and validation remain Tony's responsibility.

## Minimal invocation prompt

Use this when Claude has repository access:

`Create a Narratiive Signal for [COMPANY] ([URL]) for [RECIPIENT, ROLE]. First read and obey every canonical file in products/narratiive-signal/. Research the business using approved public sources, retain evidence lineage, produce the complete output package required by 03-generation-contract.md, and do not present final work unless it passes the canonical quality threshold.`