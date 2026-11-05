# Remaining Tony integration requirements
Planning only. No runtime or active state-reconciliation changes made.

## Existing destination
The inspected canonical checkout already has post-discovery commercial preparation in runtime/tony_post_discovery_commercial.py and review/send handling in runtime/tony_post_discovery_proposal_execution.py. Reuse that route after the active state work is complete. Do not build another email system. Its current inspected proposal-review implementation inspects text/keywords and persists subject/body; its send payload does not establish an approved PDF attachment identity. Therefore this kit does not claim that designed-PDF production, storage or attachment is already integrated.

## Required preparation packet
Use COMMERCIAL_SPECIFICATION.md as the governing specification. Tony supplies all eight items: sourced strategic findings; exact discovery statements where available; central model/formulas; conservative/upside sensitivity and assumptions; data confidence/gaps; one recommended fixed fee with costing and scope; complete two-page copy; and the Claude brief referencing DESIGN_SPEC.md. No keyword-only review can establish these requirements.

## Smallest required handoff
1. Tony assembles the structured brief and ledger from the actual completed discovery and current Groundwork, retaining source IDs and evidence status. Gaps return to Matt. Do not invoke a designer as though pricing/terms were approved.
2. Matt uses Claude to finalise the two-page design and commercial offer. Approval record names exact version, PDF SHA-256, fee and terms, actor/time, strategic/wording approval. Design review and pricing approval may be recorded separately but both must match the final PDF.
3. Tony receives the approved PDF, stores it in the existing client's commercial/proposal location using a new immutable version, and records file ID, path, version, MIME type, checksum, page count, source brief and approvals. Read back the stored file; checksum must match. Never label a path as stored without evidence.
4. Use the existing prepared commercial email. Attach the approved PDF; verify recipient, subject/body version and attachment file/hash. A link in the body is not attachment verification. Do not infer commercial approval from text/keyword checks.
5. Present the email and attachment for separate send authorisation. Bind authorisation to the recipient, exact subject/body and PDF hash. Changed content/attachment/recipient needs fresh approval. Stale approval or unresolved pricing/rights blocks dispatch.
6. Record send state only after provider evidence confirms the message/attachment; preserve current reconciliation ownership and existing separate stage-update gate. Do not change those semantics in this documentation task.

## Acceptance evidence for the later integration
A fictional rehearsal should prove missing discovery/fee/approval blocks release; mismatched/stale PDF blocks attachment/send; an approved PDF survives storage byte-identically; email shows correct attachment and recipient; send is impossible without distinct authorisation; provider failure never produces a sent state. Reuse existing test conventions when implementation is authorised. Do not exercise a live Origin send for these checks.

## Matt decisions before adoption
Validate internal day-cost estimates, provisional 55% margin assumption and bespoke fixed-fee recommendation; approve design tokens/original font/logo; confirm terms, revision allowance, bank-holiday calendar and prerequisites; confirm image rights and final scope. Recover/link the original editable master if available. Place the approved design spec and brief beside the existing proposal template through the normal versioned repository/Drive process; this handoff directory is a review artefact, not a new source of production truth.
