# Narratiive client journey certification — 23 October 2026

Status: Automated certification complete; founder-controlled live intake and candidate product adoption remain outstanding.

## Scope and safety

This certification exercised the existing journey and approval controls with
synthetic records and read-only live probes. It did not submit the public form,
send client communications, book meetings, release proposals, publish assets,
spend money or mutate production client records. The separate FIELDWORK v4 and
SKETCHBOOK v2 development branches were tested in isolation and left unchanged.

The approved customer-facing names are governed by
`docs/product/CLIENT_JOURNEY_NAMING_CANON_V1.md`. Existing workflow IDs,
persisted states, artefact names and historical records remain unchanged.

## Certification result

| Area | Result | Evidence and boundary |
| --- | --- | --- |
| Website intake | NOT TESTED | The production entry point and website-to-n8n contract were inspected read-only. The active unified inbound workflow preserves the original submission, deduplicates by submission identity, writes the canonical lead and commissions Tony once. No live form was submitted, as required. The public page still says “Blueprint Lite”; publishing the approved Groundwork wording is a separate website release. |
| Groundwork | PASS | The existing Blueprint Lite path persists the diagnostic package, commissions one durable run, routes substantive generation to the configured Claude dispatcher, retains evidence and assumptions, applies quality control and stops at an exact-version human approval gate. The synthetic replay produced no duplicate run or artefact. |
| Discovery | PASS | Approved Groundwork progressed to durable Discovery preparation. Meeting evidence ingestion requires source provenance and cannot infer approval or external action. |
| Proposal | PASS | Sourced Discovery evidence produced a bounded personalised proposal. Pricing, release, booking and external communication remain separately approval-gated. |
| Fieldwork | NOT TESTED | The deployed Growth Blueprint path passed the synthetic end-to-end checks. The latest FIELDWORK v4 candidate also passed its full isolated branch suite, but its own contract says runtime adoption is pending independent compatibility review. It was not merged or promoted by this certification. |
| Sketchbook | NOT TESTED | The existing Campaign World and Creative Bible stages passed lifecycle, lineage, handoff, quality and approval tests. The separate SKETCHBOOK v2 candidate passed its isolated branch suite, but the suite proves one scoped territory only; it does not yet prove the required two distinct concepts or one-to-two governed illustrative assets. Its canonical document also requires generic-renderer and second-client visual verification before production-ready status. |
| Telegram visibility | PASS | Live local calls through Tony’s Telegram-facing bridge returned the current mission view and four executive-visible leads with HTTP 200. No Telegram message was sent. |
| Quality assurance | PASS | Weak strategy was retained, blocked and routed back for revision; the revised artefact received a new version and passed the exact review sequence. Fieldwork and creative quality contracts passed their isolated regression suites. |
| Approval enforcement | PASS | Exact artefact checksum/version binding, explicit founder intent, proposal release controls and separate production/delivery gates all passed. No earlier approval was inherited by a downstream consequential action. |
| Failure recovery | PASS | Durable state, interruption/restart recovery, stable approval token, idempotent replay, duplicate suppression and truthful failure status all passed. |

Production end-to-end readiness is not claimed while Website intake, FIELDWORK
v4 adoption and SKETCHBOOK v2 visual/runtime adoption remain NOT TESTED in the
production path.

## Evidence summary

- The repository suite passed 1,824 tests on the certification branch.
- A focused 44-test client-journey suite passed on the deployed-code lineage.
- The isolated FIELDWORK v4 plus SKETCHBOOK v2 branch passed 1,792 tests without
  modifying or merging that branch.
- A fresh synthetic golden-path run passed all 17 acceptance proofs, including
  durable handoffs, duplicate suppression, quality failure and revision,
  restart recovery, exact-version founder approval and no external action.
- The live runtime, Tony bridge and bridge-to-runtime health round trip passed.
- The active n8n unified inbound workflow contains no email-send step in the
  intake path and only reports success after both canonical persistence and
  Tony commissioning are confirmed.

## Smallest outstanding corrections

1. Run the founder-controlled website submission below, then retain its
   evidence receipt as the production intake proof.
2. Publish the approved “Groundwork” website wording through the website’s own
   reviewed release process; do not change the API or internal Blueprint Lite
   identifier.
3. Complete the existing independent compatibility review for FIELDWORK v4,
   adopt it as a new immutable bundle only if approved, and rerun this
   certification against that exact deployed revision.
4. Add a safe two-territory SKETCHBOOK v2 fixture with one or two
   rights/provenance-tracked illustrative assets, complete second-client
   rendering and visual review, then adopt it through its existing PR and
   approval gates. Do not overwrite the Rave prototype or its historical
   assets.

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
