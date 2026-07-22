# Narratiive Signal — Generation Contract

Version: 1.1
Status: Canonical

## Instruction to the generating model

Before generating any Narratiive Signal, read every canonical file in `products/narratiive-signal/` from the latest `main` branch.

Treat those files as the source of truth. Do not invent new recipient-facing sections, rename the product, weaken the evidence standard or replace the editorial voice with generic agency language.

Confirm the repository ref used at the top of the internal work record. Do not include repository-state notes in recipient-facing material.

## Required process

1. Confirm the company, recipient, objective and available evidence.
2. Research the company, category, customers, competitors and communications using approved public sources.
3. Separate facts, interpretations and assumptions.
4. Generate at least three candidate observations internally.
5. Select the observation that is most specific, consequential, ownable and creatively fertile.
6. Build one coherent argument from observation to evidence to white space to creative direction.
7. Draft the recipient-facing Signal within the canonical word and page limits.
8. Draft the outreach email within the one-viewport rule.
9. Define the speculative campaign world and separate production prompts.
10. Score the work using `04-quality-rubric.md`.
11. Revise any dimension scoring below the threshold.
12. Return the complete package as clearly separated deliverables.

## Output separation rule

The model must produce distinct deliverables. It must not assemble the internal work record, outreach correspondence, recipient-facing Signal, production prompts and quality report into one document.

Use the following packaging:

- `INTERNAL — Work Record`
- `RECIPIENT — Outreach Email`
- `RECIPIENT — Narratiive Signal`
- `INTERNAL — Creative Production Brief`
- `INTERNAL — Quality Report`

Only the two sections marked `RECIPIENT` may be copied into client-facing communications or design files without further editing.

## Required output schema

### A. INTERNAL — Work Record

- Company
- Recipient
- Role
- Website
- Signal number
- Date
- Repository branch and commit/ref used
- Sources
- Material facts
- Interpretations
- Assumptions and confidence
- Rejected candidate observations
- Selected central insight and rationale

This section may be detailed. It must never appear inside the recipient-facing Signal.

### B. RECIPIENT — Outreach Email

- Subject line
- Email body

Rules:

- 100–150 words preferred; 180 words absolute maximum.
- Must fit within one standard laptop viewport.
- Must create interest without summarising the entire Signal.
- No source list, production notes, scoring, workflow commentary or repository references.

### C. RECIPIENT — Narratiive Signal

Return only:

- Cover/header
- Personal opening
- What we noticed
- Why we think that — no more than three evidence points
- The white space
- If this were ours...
- What we'd be careful about
- Invitation
- Optional short source footnotes

Rules:

- 500–800 words preferred; 900 words absolute maximum.
- One to two designed pages preferred; three only when a visual requires it.
- Under three minutes to read.
- One central insight, one white-space opportunity and one creative direction.
- One dominant visual or up to two concise speculative creative frames may be indicated with clear placement notes.
- Do not include the internal work record, outreach email, alternative routes, detailed treatments, prompts, scoring or review notes.
- Do not add an appendix to evade the word limit.

### D. INTERNAL — Creative Production Brief

Create the separate production brief for two assets unless instructed otherwise.

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
- final Higgsfield-ready prompt;
- suggested placement or crop in the recipient-facing Signal.

The production brief may be detailed, but it must not be pasted into the Signal. The Signal receives only the strongest approved visual output and a concise creative articulation.

### E. INTERNAL — Quality Report

- score by dimension;
- total score;
- failed gates;
- revisions made;
- confirmation of email word count;
- confirmation of Signal word count;
- confirmation that internal and recipient-facing outputs are separated;
- final approval recommendation.

## Non-negotiable rules

- One central insight, not a list of recommendations.
- Every material claim must be evidenced or clearly framed as interpretation.
- Public evidence only unless private client material has been explicitly approved.
- No invented quotes, numbers, customer attitudes or competitor activity.
- No generic praise, fake familiarity or personalisation theatre.
- No direct claim that Narratiive can guarantee growth.
- No hard meeting request or artificial urgency.
- No finished recipient-facing asset may expose internal scoring, prompts, placeholders, source scaffolding, repository notes or workflow commentary.
- Do not merge the complete output package into a single Google Doc intended for the recipient.
- If the Signal exceeds 900 words or the email exceeds 180 words, revise before returning final work.

## Tony orchestration contract

Tony should:

1. identify the next approved company in the lead or outreach queue;
2. resolve the latest canonical version of this folder from `main`;
3. give Claude the company context, evidence permissions and required files;
4. store the raw model response and source lineage immutably;
5. split and store each deliverable according to its INTERNAL or RECIPIENT status;
6. run the quality rubric and review checklist;
7. return failed work to Claude with specific deficiencies;
8. launch approved creative briefs through Higgsfield;
9. embed only approved creative previews into the recipient-facing Signal;
10. assemble the final Signal and Gmail draft without internal material;
11. notify the human approver;
12. record approval, edits, dispatch and outcome.

Tony must not silently rewrite strategic content. Strategic revisions return to Claude; orchestration and validation remain Tony's responsibility.

## Minimal invocation prompt

Use this when Claude has repository access:

`Create a Narratiive Signal for [COMPANY] ([URL]) for [RECIPIENT, ROLE]. First read and obey every canonical file in products/narratiive-signal/ from the latest main branch. Produce the five clearly separated deliverables required by 03-generation-contract.md. The recipient-facing email must fit one laptop viewport and remain below 180 words. The recipient-facing Signal must remain below 900 words, contain one central insight and exclude all internal workflow, evidence scaffolding, prompts and scoring. Research the business using approved public sources, retain evidence lineage internally, and do not present final work unless it passes the canonical quality threshold.`