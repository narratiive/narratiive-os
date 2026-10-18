# Issue 477 focused release sequence

Status: candidate release preparation only. **Do not merge or deploy without
the applicable independent review and human decision.**

PR #478 remains the audit record for the combined investigation. The focused
pull requests isolate review and rollback as follows.

## Proposed order

1. **PR #479 — operational reliability and idempotency.**
   Review and merge first because it repairs integration behaviour without
   selecting a new FIELDWORK production contract. Deployment remains a separate
   operational action. Roll back by reverting the merge commit and restoring
   the recorded pre-deployment runtime backup; do not restore only one component
   of an async handoff.
2. **PR #480 — FIELDWORK commissioning and quality gates.**
   Review after #479. The founder-argument contract remains opt-in, so merge does
   not change the production default. Roll back by reverting the merge commit;
   prior commissioning remains available and existing artefacts remain immutable.
3. **PR #481 — SKETCHBOOK canonical template candidate.**
   This is stacked on #480 so it can reuse the established Rave design tokens and
   evidence boundary. Rebase onto `main` only after #480 is merged. Roll back by
   reverting the template commit; no runtime or production default depends on it.

## Dependencies and gates

| Change | Depends on | Before merge | Before deployment or use |
| --- | --- | --- | --- |
| #479 | Existing runtime and credentials | Green CI, exact-commit independent review, diff/security review | Explicit operational deployment authorisation, backup, health check, unattended proof |
| #480 | Existing Claude provider path and research inputs | Green CI, product-contract review, exact-commit independent review | Matt approves opt-in use; production default remains unchanged |
| #481 | #480 design/evidence conventions | Render validation, five-page visual QA, exact-commit independent review | Matt approves creative direction and exact artefact version before client-facing use |

## Regression evidence required

- #479: full Python suite plus focused Gmail, Tony async, OAuth and idempotency
  tests stated in the PR.
- #480: full Python suite plus founder-argument schema, strict missing-field,
  editorial QA and three-business calibration tests.
- #481: presentation package/layout validation, five-page PDF inspection,
  machine-readable template validation and repository full suite.

Google Drive review copies are delivery derivatives. The committed artefacts,
checksums and source lineage remain authoritative; a Slides copy does not gain
client approval or replace repository history.
