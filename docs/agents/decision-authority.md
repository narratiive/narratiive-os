# Narratiive OS Decision Authority

Status: Decision-routing companion to the AI Constitution

`ai-constitution.md` is the canonical source for role authority, ownership,
responsibilities, prohibitions, and reserved decisions. This document does not
redefine those roles. It tells contributors how to classify a proposed change
and route its review and decision.

## Decision terms

- **Proposes:** frames the change and supplies evidence and consequences.
- **Owns execution:** prepares the branch, artefacts, implementation, or
  operational action after authority is established.
- **Decides:** gives the required approval for the decision class.
- **Reviews:** provides independent domain review; the author cannot fill this
  role for their own work.
- **Consulted:** supplies relevant evidence but does not approve the decision.
- **Record:** the durable place where the proposal, reviews, decision, and
  resulting version are traceable.

Approval of a decision does not remove the pull-request, independent-review,
human-release, lineage, or immutable-history requirements in the Constitution.
No decision class or exception can waive the Constitution's non-waivable
invariants.

## Change classification

### Substantive governance change

A change is substantive when it changes meaning, authority, obligation, risk, or
enforcement. Examples include:

- role authority, responsibility, prohibition, delegation, or reserved decision;
- stream ownership, forbidden-folder boundaries, or cross-stream review;
- branch, pull-request, approval, merge, release, or exception policy;
- client-facing approval, evidence permissions, lineage, immutability,
  workspace/client isolation, security, or credential rules;
- architecture invariants or boundaries;
- product canon, external naming, quality gates, or client promise;
- workflow stages, state, handoffs, revision ownership, or completion criteria;
- permitted use of an existing tool, provider, automation, export, or production
  handoff;
- GitHub settings or other configuration that enforces governance.

Substantive governance changes require the full review stated in the matrix
below. When a change affects more than one decision class, apply the union of
required reviews. Matt decides constitutional, role-authority, product-canon,
client-promise, and governance-exception changes.

### Non-substantive documentation change

A change is non-substantive only when it preserves meaning and enforcement, such
as:

- spelling, punctuation, grammar, or formatting corrections;
- repairing an internal link or file reference;
- removing exact duplication in favour of a canonical reference;
- clarifying wording without changing who may decide, act, review, or approve;
- updating an accurate inventory after an already approved repository change,
  without adding policy or capability.

Non-substantive documentation changes use lightweight review: one independent
reviewer familiar with the owning document, normal pull-request checks, and an
authorised merger other than the author. They do not require the full
cross-functional review or Matt's decision.

If reasonable reviewers could disagree about whether meaning changed, classify
the change as substantive.

## Decision matrix

| Decision class | Proposes | Owns execution | Decides | Required independent review | Record |
| --- | --- | --- | --- | --- | --- |
| Constitutional, role-authority, or governance exception | Any role may raise it | Executive Layer | Matt | ChatGPT, Codex, Claude Code; Tony when operations are affected | Pull request and explicit Matt decision |
| Non-substantive governance documentation | Document owner or contributor | Executive Layer | Independent document reviewer | One reviewer other than the author | Pull request |
| Material architecture or cross-stream interface | ChatGPT or affected owner | Codex for code; Executive Layer for architecture docs | ChatGPT within approved company/product intent; Matt when commercially, legally, operationally, or reputationally material | Codex and every affected stream; Claude Code for product impact | Pull request, tests, and architecture decision rationale |
| Runtime, schema, CI, script, bridge, operations, or technical configuration implementation | Codex | Worker Infrastructure | Independent authorised technical reviewer | ChatGPT when a boundary or invariant changes; affected streams as applicable | Pull request and test/check results |
| Product canon, external name, quality gate, or client promise | Claude Code | Commercial or Delivery owner | Matt | ChatGPT for system impact; Codex for implementation/migration impact | Pull request, canon version/changelog, and Matt decision |
| Specialist, workflow, template, or prompt contract | Delivery owner or responsible specialist | Delivery Engine; Codex for executable impact | Claude Code for product contract within existing canon; Matt if canon/client promise changes | Specialist owner, Codex for runtime compatibility, ChatGPT for boundary changes | Pull request and versioned contract |
| Commercial target, prospect/client selection, or evidence permission | Matt, Claude Code, or delegated commercial owner | Commercial Engine | Matt or explicitly delegated authorised human | Claude Code for product use; Tony for operational readiness | Client/work record and approval record where applicable |
| Client-facing artefact release, dispatch, publication, export, or production use | Producing specialist or Claude Code submits | Tony routes; responsible tool performs approved action | Authorised human for the exact artefact version | Quality Reviewer and applicable product checklist | Append-only approval and dispatch/export record |
| Routine run, queue, retry, or handoff inside an approved workflow | Tony or the runtime | Tony through the public command boundary | Tony within the approved contract; human decision at approval gates | Responsible specialist for defects; Codex for technical failures | Run state, events, jobs, artefacts, and approval history |
| GitHub governance configuration | ChatGPT or Codex | Codex or authorised repository administrator | Authorised repository administrator; Matt for policy exceptions | Independent technical reviewer and ChatGPT | Pull request where file-backed plus GitHub settings/audit record |
| Existing provider, research adapter, export, or production-tool use | Responsible stream owner | Tony or Worker Infrastructure through the existing boundary | Role allowed by the approved workflow; authorised human for client-facing output | Codex for technical configuration, Claude Code for product output, Quality Reviewer before release | Routing, lineage, tool result, and approval records supported by the existing workflow |

## Delegation and absence

- Matt may explicitly delegate a defined class of human approval or repository
  administration. The delegation must name its scope, delegate, duration or
  revocation condition, and record location.
- Delegation does not permit the delegate to approve or merge their own work.
- An AI agent cannot infer delegation from access, prior behaviour, a role title,
  or a successful tool call.
- When the required decider is unavailable, the affected action waits or is
  marked blocked. Operational urgency does not transfer authority.

## Repository policy and repository configuration

### Repository policy

The governance documents state mandatory repository policy:

- nobody edits `main` directly;
- work uses branches and pull requests;
- authors do not approve or merge their own work;
- required independent and human approvals are obtained;
- required checks pass before merge.

These rules apply even when a hosting platform does not technically prevent a
violation.

### Repository configuration

GitHub configuration is the technical enforcement layer. Relevant settings may
include branch protection or rulesets, pull-request requirements, required
approvals, dismissal of stale approvals, required status checks, conversation
resolution, and restrictions on direct pushes or force pushes.

The repository contains `.github/workflows/runtime-tests.yml`, which defines
runtime test automation. Files in the checkout do not prove that branch
protection, rulesets, required reviewers, or merge restrictions are enabled on
GitHub. Their current state must be verified in GitHub settings by an authorised
repository administrator.

A missing or weaker GitHub setting is an enforcement gap, not permission to
ignore repository policy. Changing an enforcement setting is a substantive
governance change and follows the full applicable review path.
