# Narratiive OS Agent Governance

This file is the repository entry point for every human or AI contributor. It
governs the whole repository. More specific instructions may add constraints,
but may not weaken this file, the product canon, evidence rules, approval gates,
or immutable history.

## Required reading

Before proposing or changing anything, read:

1. `docs/agents/ai-constitution.md`
2. `docs/agents/decision-authority.md`
3. `docs/agents/product-canon.md`
4. `docs/agents/architecture.md`
5. `docs/agents/stream-ownership.md`
6. `docs/agents/workflow-contracts.md`
7. `docs/agents/coding-standards.md`
8. The README, agent contract, workflow, product canon, template, tests, and
   source files relevant to the requested change.

Do not begin from a generic architecture or remembered product description.
The checked-out repository is the source of truth.

## Non-negotiable rules

- Preserve the names `Narratiive OS`, `Narratiive Growth Blueprint`,
  `Growth Blueprint`, `Campaign World`, `Creative Director's Bible`,
  `Growth Specification`, `Production Pack`, `Asset Manifest`,
  `Performance Feedback`, `Mission Control`, `Narratiive Signal`, and
  `Opportunity Card Pipeline`.
- Preserve the existing five-stage Growth Blueprint pipeline and its specialist
  ownership:
  Research Analyst, Strategy Director, Campaign World Generator, Creative
  Director, and Quality Reviewer.
- Preserve the separate Growth Specification object lifecycle and do not treat
  its objects as interchangeable with the older workflow templates.
- Do not edit `main` directly. Work on a branch and submit a pull request.
- Do not approve or merge your own work. AI agents may not count their own
  review as approval.
- An authorised human must approve every client-facing output before release,
  dispatch, publication, presentation export, or production use.
- Never invent evidence, claims, client facts, research, proof points, approval,
  lineage, or completion state. State missing inputs and uncertainty explicitly.
- Preserve evidence lineage from source to research, strategy, campaign,
  creative direction, quality review, and exported artefact.
- Preserve append-only event and memory history. Corrections are new events or
  versions, never rewrites of prior records.
- Preserve immutable artefacts and canonical assets. Create a new version and
  retain parent references; do not overwrite or delete history.
- Preserve workspace and client isolation. Never move or expose data across
  workspaces to make a task easier.
- Preserve template headings, marker comments, tables, YAML contracts, section
  order, and unresolved placeholders unless an approved canon change explicitly
  requires otherwise.
- Secrets belong in runtime configuration or environment variables. Never put
  credential values in code, prompts, events, artefacts, routing metadata, test
  fixtures, or documentation.
- Orchestrators coordinate and validate. They do not silently perform or rewrite
  specialist work.
- Quality review is advisory until the required human approval is recorded.
- Keep changes within the assigned workstream. A cross-stream change must be
  declared in the pull request and reviewed by every affected stream owner.

## Roles and authority

`docs/agents/ai-constitution.md` is the canonical source for role authority,
responsibilities, prohibitions, boundaries, and reserved decisions.
`docs/agents/decision-authority.md` classifies changes and routes decisions and
reviews. Other governance files must reference those sources rather than
restate role authority.

The Constitution controls interpretation of this entry point. The invariants
restated above are non-waivable; no role or exception process may bypass
evidence, lineage, immutable history, workspace/client isolation, credential
security, independent review, or human approval.

## Repository change contract

Before editing:

- inspect `git status`, the active branch, relevant history, and local
  instructions;
- identify the owning workstream and affected downstream consumers;
- inspect existing tests and conventions;
- leave unrelated and generated local files untouched.

While editing:

- make the smallest coherent change;
- do not add runtime functionality to a documentation-only task;
- update documentation when a changed contract would otherwise become false;
- retain backward compatibility unless the approved task explicitly changes it.

Before handoff:

- run the tests and checks proportionate to the change;
- inspect the complete diff for scope, secrets, client data, terminology,
  lineage, and approval-gate regressions;
- report tests run, assumptions, unresolved risks, and affected streams;
- do not commit, push, approve, merge, publish, export, or send unless the user
  explicitly authorises that specific action.

## Canon and conflict handling

Do not resolve a conflict by silently choosing whichever instruction is most
convenient.

- Product-specific canon governs product content and quality.
- Canon locked by `knowledge/blueprint/manifest.json` is read-only production IP.
- Executable runtime behaviour is established by source code, executable
  workflow definitions, and tests; descriptive documentation must not claim a
  different implementation state.
- A direct decision from Matt may change canon, but the decision and resulting
  version change must be recorded through the normal branch and pull-request
  process.
- If two applicable sources remain inconsistent, stop the affected work, record
  the conflict, and route it to the relevant owner.

## Local verification

The existing runtime test command is:

```bash
python -m unittest discover -s tests -v
```

Python 3.10 or newer is required by the repository; CI currently runs the suite
on Python 3.12. Do not invent new mandatory tooling without an approved change.
