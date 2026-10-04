# Narratiive Golden Path lifecycle

Status: canonical runtime interpretation

Narratiive uses two related but distinct levels of state. Customer lifecycle
describes the commercial relationship. Operational workflow state describes
the governed work inside that lifecycle stage. A completed worker call is never
itself a customer-lifecycle transition.

## Level A — customer lifecycle

| Canonical lifecycle | Compatible persisted labels | Entry evidence | Permitted next lifecycle | Owner | Completion evidence |
| --- | --- | --- | --- | --- | --- |
| `LEAD` | `lead`, outbound `research`/`outreach` | scoped opportunity or diagnostic identity | `BLUEPRINT_LITE` (inbound) or `DISCOVERY` after the established outbound path | Tony/commercial owner | qualified opportunity evidence |
| `BLUEPRINT_LITE` | `blueprint_lite`; legacy `narrative_shift` | complete Growth Diagnostic input package | `DISCOVERY` | Strategy specialist; Tony orchestrates | immutable Blueprint Lite plus exact-version human decision |
| `DISCOVERY` | legacy `meeting` | approved Blueprint Lite and scoped client/opportunity | `PROPOSAL` | Account/Strategy specialist | sourced Discovery evidence and durable preparation artefact |
| `PROPOSAL` | `proposal` | sourced Discovery evidence | `DELIVERY` when the Growth Sprint is explicitly accepted | commercial owner | immutable Growth Sprint proposal and acceptance evidence |
| `DELIVERY` | `delivery` | accepted Growth Sprint scope | `COMMERCIAL` or `COMPLETE` according to the engagement | Tony orchestrates specialists | governed Research, Strategic Synthesis, Strategy Thesis and Growth Blueprint artefacts |
| `COMMERCIAL` | legacy `invoice` | agreed commercial obligation | `COMPLETE` | authorised commercial/finance owner | invoice/payment or other applicable commercial evidence |
| `COMPLETE` | `complete` | delivery and applicable commercial obligations complete | none | authorised owner | closure record with durable evidence |

`MEETING` is therefore a storage-compatible label for `DISCOVERY`.
`INVOICE` is a storage-compatible operational/commercial record inside
`COMMERCIAL`; it is not the complete commercial relationship. Existing records
remain readable and are not migrated destructively.

## Level B — operational workflow state

The executable truth is the workflow registry and persisted run state. The
following table names the canonical operational meaning without duplicating
equivalent executable states.

| Lifecycle | Operational state | Entry evidence | Transition / owner | Required artefact | Quality gate | Human gate | External-action gate | Failure / retry | Completion evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `BLUEPRINT_LITE` | queued → generating → ready for review → changes requested / approved | diagnostic package | `growth_diagnostic_to_blueprint_lite`; Strategy specialist | Blueprint Lite | deterministic Blueprint Lite contract | exact artefact/version/checksum | separately required for any send | bounded worker retries; revision creates a new version | immutable artefact and approval history |
| `DISCOVERY` | awaiting discovery → preparation generating → preparation ready → complete | approved Blueprint Lite; sourced meeting evidence for completion | `blueprint_lite_to_discovery_preparation`; Tony routes Strategy | Discovery Preparation | discovery preparation contract | preparation review; meeting decisions remain human | booking/contact separately gated | block on missing evidence; bounded revision | preparation artefact plus sourced Discovery evidence |
| `PROPOSAL` | generating → ready for review → changes requested / approved → accepted/rejected | sourced Discovery evidence | `discovery_evidence_to_growth_sprint_proposal`; commercial specialist | Growth Sprint proposal | proposal contract | proposal approval and commercial acceptance are explicit | sending separately gated | bounded retry/revision | immutable proposal plus acceptance evidence |
| `DELIVERY` | commissioned → research → strategic synthesis → strategy thesis → growth blueprint | accepted Growth Sprint scope | deterministic registered handoffs; Tony orchestrates, specialists produce | one immutable artefact per workflow | stage contract plus senior-strategist review before Blueprint human review | Strategy Thesis and final Growth Blueprint are exact-version Matt gates | delivery/publication/spend remain separate | timeout/provider/malformed/truncated/persistence failures block or retry; quality failure routes upstream; retry exhaustion escalates | run snapshots, append-only events, artefacts, lineage and approvals |
| `COMMERCIAL` | obligation recorded → invoice pending/issued → reconciled | approved commercial terms | authorised commercial/finance process | applicable commercial record | schema/evidence validation | authorised human | any external issue/send uses its action gate | explicit blocked/reconciliation state | verified commercial evidence |

## Delivery sequence and gate classes

The canonical Growth Blueprint delivery path is:

`Growth Diagnostic → Blueprint Lite → Discovery Preparation → sourced Discovery
evidence → Growth Sprint proposal/acceptance → Research → Strategic Synthesis →
Strategy Thesis → Growth Blueprint candidate → senior-strategist review → Matt
review`.

Three gates are deliberately separate:

1. **Quality gate:** deterministic contracts and the independent senior review
   decide whether the work is fit to show Matt. A failed review routes the
   immutable candidate back to its producing specialist with revision reasons.
2. **Human judgement gate:** Matt approves, rejects or requests revision against
   the current run, artefact ID, version, checksum, approval token and verbatim
   instruction. Ambiguous language is never a decision.
3. **External-action gate:** sending, publishing, production, advertising
   mutation and spend each require their own exact action approval and verified
   receipt. Artefact approval does not grant external authority.

## Recovery and no-false-success contract

- Duplicate enqueue/handoff identities load the existing run or fail on input
  conflict; they do not duplicate work.
- Running stages recover to a retryable durable state after restart.
- Provider timeout and execution failure use bounded retries, then block.
- Malformed or truncated output is rejected and never promoted.
- Every failed quality candidate is retained as an immutable attempt artefact.
- Revision increments the producing stage version, records its reason and
  superseded artefact, then re-runs downstream review.
- A stale token, version or checksum fails closed.
- Missing evidence produces a block or explicit escalation, never a guess.
- External denial or missing receipt never becomes a success event.

Creative, Media, Measurement and Client Operations remain downstream
capabilities. They are not prerequisites for certifying the Growth Blueprint
Golden Path and must not be reported complete without their own durable runs.
