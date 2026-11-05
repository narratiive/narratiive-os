# Fieldwork proposal production and review

This is the Pass 2 integration of the approved v4 template into the existing
`discovery_evidence_to_growth_sprint_proposal` workflow. Historical workflow and
stage IDs remain unchanged. The detailed strategic/financial work product is
retained as immutable JSON; the human review copy is the separate two-page
Fieldwork PDF. The historical seven-page output remains readable in history,
but cannot pass current quality, approval or simulated-send checks.

## Preparation and quality

The preparation contract now includes `fieldwork_proposal`: the complete input
shape documented in `templates/fieldwork/v4/README.md`. The existing internal
brief fields remain required. The copy specialist receives template guidance
and explicit evidence, assumption and fictional-discovery rules. Its proposed
fee must match `commercial_proposal_inputs.proposed_fee`; its timeline must be
`7 working days`. The proposed fee is not an approved fee. Client-facing copy
and the email draft use Fieldwork; internal compatibility identifiers remain.

Current template limitations remain explicit: internal candidates, proposed GBP
fees excluding VAT, the illustrative account-revenue model and exact approved
Mac fonts. Rendering is unavailable without those fonts; it never substitutes a
generic PDF. Missing real discovery does not become a discovery statement.
Source and image rights still need human review before real release. Real
client sending is disabled in the canonical action-preview service.

## Exact review package

`HumanReviewPresentationService` selects the approved renderer for this workflow.
It validates the input workspace/client and immutable source checksum, stores
and reads back the two-page PDF through `HumanReviewArtifactStore`, and retains
`fieldwork-validation.json` plus `client-email-draft.json` alongside it.
The existing manifest includes `proposal_review`, the exact PDF hash, proposed
fee, template version and email draft hash. The email draft identifies the PDF
and source hashes, is visibly unapproved, has no authorised client email address,
and grants no send authority.

Existing internal review delivery sends the actual PDF and proposed email text
only to the authorised Narratiive review address. Its verified receipt remains
idempotent and source/version bound. Telegram carries the client, Proposal
stage, Matt's review action and verified review-email location.

A content approval is still made through the current exact-source approval
binding. Before accepting it, the runtime validates/renders the current
Fieldwork package and records its exact PDF, fee/scope and email identity in the
append-only approval binding. It never changes `proposed_fee.approved` in the
immutable source. A legacy proposal cannot acquire this binding.

The existing simulated-send preview requires that exact commercial/PDF binding
and its matching draft identity. The separate action digest binds the resolved
recipient, subject, body and attachment. A stale/missing approval, modified PDF,
provider failure or lack of a distinct action authorisation cannot become a
verified send. Only the existing internal simulation recipient is supported;
this work does not enable real client contact. The older text-only proposal
execution wrapper now blocks new and previously persisted pending sends, while
retaining history and already-verified Notion receipt handling.

## Existing proposal revisions

An authorised request through the existing `revise` command may additionally
supply `inputs.fieldwork_revision_inputs`. It must contain a complete, validated
renderer input matching the existing run's workspace/client. It is recorded
atomically with the existing revision request, never applied by editing a run
file. The new attempt uses the supplied reference copy unchanged and asks the
specialist to reconcile the separate internal brief and email. Accepted output
creates a new immutable version with previous-artefact lineage. The prior
proposal and all prior approvals remain intact. No proposal approval is implied
by requesting its revision.

For Origin, supply the existing v4 fictional input with the canonical workspace
and client IDs. Keep the £9,800 fee pending, retain illustrative assumptions and
absence-of-discovery disclosures, and stop when the new candidate reaches
Matt's review gate. Do not send a client simulation, accept terms, record payment
or commission Fieldwork as part of this integration.

## Verification

Use the focused proposal, human-review, action-preview, workflow, revision and
legacy-send regression tests. Generic lifecycle tests use an explicitly labelled
reference-PDF fixture on Linux hosts without licensed Mac fonts; they exercise
workflow contracts, not visual rendering. Dedicated rendering tests use the
actual fonts on the Mac and explicitly skip if unavailable. Mac visual QA and
real internal-review delivery remain required operational evidence.
