# Narratiive client journey certification — 23 October 2026

Status: Live intake and Groundwork verified; downstream production-candidate adoption remains outstanding.

## Scope and safety

This certification exercised the existing journey and approval controls with a
clearly marked synthetic production record and isolated simulations. It called
the production website intake API but did not submit the browser form. It did
not send client communications, book meetings, release proposals, publish
assets or spend money. The test record was marked `test` for reporting
exclusion. The separate FIELDWORK v4 and SKETCHBOOK v2 development branches
were tested in a disposable compatibility worktree and left unmerged.

The approved customer-facing names are governed by
`docs/product/CLIENT_JOURNEY_NAMING_CANON_V1.md`. Existing workflow IDs,
persisted states, artefact names and historical records remain unchanged.

## Certification result

| Area | Result | Evidence and boundary |
| --- | --- | --- |
| Website intake | PASS — live integration verified | Production API submission `31` persisted once; replay returned `already_stored` and `duplicate=true`. Canonical lead `4020c9cf-a8f2-8147-92a7-dce0ebc9ec41` was marked `test`. No browser form or client communication was submitted. |
| Groundwork | PASS — live integration verified | Production run `31` retained one research/Claude attempt, passed every quality check, persisted one immutable version and is `awaiting_approval`. Tony's live `/workflow 31` Telegram path returned the same state with `external_action_taken=false`. |
| Discovery | PASS — automated test | Approved Groundwork progresses to durable Discovery preparation in the isolated acceptance suite. Meeting evidence requires source provenance and cannot infer approval or external action. The live production record was not falsely approved to enter this stage. |
| Proposal | PASS — automated test | Sourced synthetic Discovery evidence produces a bounded personalised proposal. Current product naming is now validated across every field rendered into the review PDF. Pricing, release, booking and communication remain separately approval-gated. |
| Fieldwork | PASS — automated compatibility; NOT DEPLOYED | The current runtime lineage plus FIELDWORK v4 and SKETCHBOOK v2 passed 1,843 tests. FIELDWORK v4 remains a draft candidate and was not promoted to production. |
| Sketchbook | PASS — automated compatibility; NOT DEPLOYED | The stacked candidate contains Rave and KatKin five-page review packages, two concepts and governed illustrative assets with visual-review/provenance records. It passed the combined 1,843-test suite but remains a draft candidate, so production capability is not certified. |
| Telegram visibility | PASS — live integration verified | Tony's authenticated Telegram-facing `/workflow 31` path returned the production Groundwork run at its human approval gate with HTTP 200. No Telegram message was sent. |
| Quality assurance | PASS | Weak strategy was retained, blocked and routed back for revision; the revised artefact received a new version and passed the exact review sequence. Fieldwork and creative quality contracts passed their isolated regression suites. |
| Approval enforcement | PASS | Exact artefact checksum/version binding, explicit founder intent, proposal release controls and separate production/delivery gates all passed. No earlier approval was inherited by a downstream consequential action. |
| Failure recovery | PASS | Durable state, interruption/restart recovery, stable approval token, idempotent replay, duplicate suppression and truthful failure status all passed. |

Production end-to-end readiness is not claimed while Discovery onward has not
been exercised through the deployed production services and FIELDWORK v4 plus
SKETCHBOOK v2 remain unmerged draft candidates.

## Evidence summary

- Naming/review code commit `9662dfe1c4ba775358ba48560e337b86609118e9`
  passed `python -m unittest discover -s tests` with 1,829 tests on 23 October
  2026. PR #492 records the exact-head CI result and independent review history.
- The combined compatibility worktree used current runtime base
  `b9a55469e307a377cf4c376d4f5563f00ce726bb` and stacked FIELDWORK/SKETCHBOOK
  candidate `88fe7347db9dbddff456d73dfbe5e06ad651fb9f`; 1,843 tests passed. PRs #485
  and #486 retain the candidate lineage. Neither candidate was merged.
- `scripts/run_golden_path_certification.py` passed all 17 synthetic acceptance
  proofs, including durable handoffs, duplicate suppression, quality failure and
  revision, restart recovery, simulated exact-version founder approval and no
  external action. Receipt `golden-path-20261023-0b67e6de325e`, generated
  `2026-10-23T13:43:06Z`. This is automated evidence, not a live founder decision.
- Live receipt: website submission `31`, canonical test lead
  `4020c9cf-a8f2-8147-92a7-dce0ebc9ec41`, workflow run `31`, updated
  `2026-10-23T13:31:40Z`. The protected local records are
  `.runtime/blueprint-lite-preparation.json` key `31` and
  `$TONY_WORKFLOW_RUNTIME_ROOT/5816772411096ecf1b688973/runs/31.json`.
- The live workflow and Telegram status calls both reported
  `awaiting_approval`, approval `pending`, and no external action. The first
  persistence attempt exposed a stale presentation-skill cache path; the mode-600
  runtime environment was backed up and corrected, Tony's bridge and conversation
  worker alone were restarted, and the exact persisted evidence was recovered
  without a second hosted-model call.

## Smallest outstanding corrections

1. Publish the approved “Groundwork” website wording through the website’s own
   reviewed release process; do not change the API or internal Blueprint Lite
   identifier.
2. Complete the existing independent compatibility review for FIELDWORK v4,
   adopt it as a new immutable bundle only if approved, and rerun this
   certification against that exact deployed revision.
3. Complete SKETCHBOOK v2's existing PR review and approval gate, then verify its
   Rave and KatKin packages through the deployed runtime without overwriting
   either candidate or its historical assets.

## Founder-controlled live test plan

Entry point: `https://narratiive.com/diagnostic/`

Use a unique company label such as
`FOUNDER CERTIFICATION 2026-10-23 — DO NOT CONTACT` and a founder-controlled
email alias. Do not use a real prospect. Record the browser submission ID and
submission time.

Expected checkpoints:

1. The browser confirms `stored` or `already_stored`, Groundwork preparation is
   `queued`, and delivery remains `unconfirmed`.
2. Exactly one matching record appears in `Leads — CANONICAL`, retaining the
   original answers, scores, blockage, recommended actions and submission ID.
3. Mark the record as a test with the existing `mark_test` attention control so
   it is excluded from commercial reporting and proactive attention views.
4. Tony’s `/leads` and `/mission` views show the correctly labelled record and
   one durable Groundwork run before suppression; no duplicate client or
   artefact exists.
5. Research and drafting retain sources, assumptions and evidence lineage, and
   the Groundwork result stops at Matt’s exact-version approval gate.
6. No email, calendar booking, Drive share, proposal release, asset delivery or
   publication occurs without a separate explicit approval.
7. Replay the same submission ID once through the controlled test harness. The
   existing lead and run must be reused, with no second email, client record or
   artefact.
8. After evidence is captured, leave the record marked as test and archived or
   suppressed under the existing retention policy; do not delete production
   history to make the test disappear.
